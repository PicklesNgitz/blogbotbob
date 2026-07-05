from __future__ import annotations

import logging
import math
import sqlite3
from pathlib import Path

import yaml
from pydantic import BaseModel

from blogbot.agents import PipelineHalt
from blogbot.config import Config, Secrets
from blogbot.db import drafts_by_status, insert_vote, update_draft, utc_now
from blogbot.llm.base import LLMError
from blogbot.llm.router import Role, get_client
from blogbot.models import DraftStatus, PanelVote

logger = logging.getLogger(__name__)

_SCHEMA_HINT = '{"score": number, "critique": "one paragraph, max 80 words"}'


class DraftVerdict(BaseModel):
    title: str
    score: float
    verdict: str  # "selected" | "rejected"


class PanelReport(BaseModel):
    verdicts: list[DraftVerdict] = []
    k: int = 0


def _load_personas(personas_file: str) -> list[dict]:
    path = Path(personas_file)
    if not path.exists():
        path = Path("personas.yaml")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("personas", [])


def run_panel(
    conn: sqlite3.Connection,
    config: Config,
    secrets: Secrets,
    run_id: str,
) -> PanelReport:
    personas = _load_personas(config.panel.personas_file)
    if len(personas) != config.panel.scores_per_draft:
        raise PipelineHalt(
            f"persona count ({len(personas)}) does not match config.panel.scores_per_draft "
            f"({config.panel.scores_per_draft}) — update personas.yaml or config.yaml"
        )

    drafts = drafts_by_status(conn, DraftStatus.generated, run_id=run_id)
    if not drafts:
        raise PipelineHalt("no generated drafts for this run; run generate first")

    client = get_client(Role.PANEL, config, secrets)

    for draft in drafts:
        scores: list[float] = []
        for persona in personas:
            system = (
                "You role-play exactly this reader and judge a blog draft strictly from "
                f"their perspective. Persona: {persona['profile']}\n"
                "Answer ONLY JSON."
            )
            user = (
                "Draft:\n---\n"
                f"{draft.markdown}\n"
                "---\n"
                "Score this draft 0-10 for how valuable and credible it is TO YOU.\n"
                "Be harsh; 8+ means you would share it.\n"
                f"JSON schema: {_SCHEMA_HINT}"
            )

            score = 5.0
            critique = ""
            for attempt in range(2):
                try:
                    result = client.complete_json(system, user, _SCHEMA_HINT, max_tokens=256)
                    raw_score = float(result.get("score", 5.0))
                    score = max(0.0, min(10.0, raw_score))
                    critique = str(result.get("critique", ""))
                    break
                except Exception as e:
                    if attempt == 1:
                        score = 5.0
                        critique = f"[vote failed: {e}]"
                        logger.warning("panel: draft %d persona %s vote failed: %s", draft.id, persona["name"], e)

            vote = PanelVote(
                draft_id=draft.id,  # type: ignore[arg-type]
                persona=persona["name"],
                score=score,
                critique=critique,
                created_at=utc_now(),
            )
            insert_vote(conn, vote)
            scores.append(score)

        mean_score = sum(scores) / len(scores) if scores else 5.0
        update_draft(conn, draft.id, panel_score=mean_score, status=DraftStatus.scored.value)  # type: ignore[arg-type]

    # Selection: top-k
    scored_drafts = drafts_by_status(conn, DraftStatus.scored, run_id=run_id)
    scored_drafts.sort(key=lambda d: d.panel_score or 0.0, reverse=True)

    raw_k = math.ceil(len(scored_drafts) * config.run.panel_top_fraction)
    k = max(1, min(raw_k, config.run.max_publishes_per_run))

    report = PanelReport(k=k)
    for i, draft in enumerate(scored_drafts):
        verdict = "selected" if i < k else "rejected"
        new_status = DraftStatus.selected if i < k else DraftStatus.rejected
        update_draft(conn, draft.id, status=new_status.value)  # type: ignore[arg-type]
        report.verdicts.append(
            DraftVerdict(title=draft.title, score=draft.panel_score or 0.0, verdict=verdict)
        )
        logger.info("panel: %s score=%.1f → %s", draft.title, draft.panel_score or 0.0, verdict)

    return report
