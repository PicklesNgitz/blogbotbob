from __future__ import annotations

import json
import logging
import sqlite3

from blogbot.agents import PipelineHalt
from blogbot.config import Config, Secrets
from blogbot.db import angles_for_run, insert_angle, set_topic_status, topics_by_status, utc_now
from blogbot.llm.router import Role, get_client
from blogbot.models import Angle, TopicStatus

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an editorial strategist for a technology blog aimed at small and "
    "medium business decision-makers interested in practical AI adoption. "
    "You identify which trending topics are worth writing about and propose "
    "concrete article angles. You answer ONLY with JSON."
)

_SCHEMA_HINT = '{"angles": [{"title": str, "rationale": str, "priority": int, "topic_ids": [int]}]}'


def run_analysis(
    conn: sqlite3.Connection,
    config: Config,
    secrets: Secrets,
    run_id: str,
) -> list[Angle]:
    topics = topics_by_status(conn, TopicStatus.new)
    if len(topics) < 3:
        raise PipelineHalt("not enough topics; run scrape first")

    # Cap digest at 120; sort by raw_score desc, then newest fetched_at desc
    sorted_topics = sorted(topics, key=lambda t: (-t.raw_score, -(t.id or 0)))[:120]
    valid_ids = {t.id for t in sorted_topics if t.id is not None}

    lines = []
    for t in sorted_topics:
        summary_snip = (t.summary or "")[:200]
        lines.append(f"[{t.id}] ({t.source}, score {t.raw_score}) {t.title} — {summary_snip}")
    digest = "\n".join(lines)

    n_angles = config.drafting.posts_per_run
    user_prompt = (
        f"Here are trending items collected today:\n\n{digest}\n\n"
        f"Propose the {n_angles} best article angles. Rules:\n"
        "- Each angle must cite which item ids inspired it.\n"
        "- Angles must be practical for SMB readers, not academic.\n"
        "- No two angles may cover substantially the same story.\n"
        "- Prioritize: 1 = strongest.\n\n"
        f"JSON schema:\n{_SCHEMA_HINT}"
    )

    client = get_client(Role.ANALYSIS, config, secrets)
    raw = client.complete_json(_SYSTEM, user_prompt, _SCHEMA_HINT, max_tokens=2048)

    raw_angles = raw.get("angles", [])
    now = utc_now()
    inserted: list[Angle] = []

    for item in raw_angles:
        raw_ids: list[int] = item.get("topic_ids", [])
        valid_topic_ids = [i for i in raw_ids if i in valid_ids]
        if not valid_topic_ids:
            logger.warning("angle %r dropped: no valid topic_ids in digest", item.get("title"))
            continue

        angle = Angle(
            run_id=run_id,
            title=item.get("title", ""),
            rationale=item.get("rationale", ""),
            priority=int(item.get("priority", 99)),
            topic_ids=json.dumps(valid_topic_ids),
            created_at=now,
        )
        angle_id = insert_angle(conn, angle)
        angle.id = angle_id
        inserted.append(angle)

    if not inserted:
        raise PipelineHalt("analysis produced no valid angles")

    digested_ids = [t.id for t in sorted_topics if t.id is not None]
    set_topic_status(conn, digested_ids, TopicStatus.analyzed)

    logger.info("analysis: %d angles inserted", len(inserted))
    return inserted
