"""test_panel.py — panel selection math and vote failure."""
import json
import math

import pytest

from blogbot.agents import PipelineHalt
from blogbot.agents.panel import run_panel
from blogbot.config import load_config, load_secrets
from blogbot.db import insert_draft, update_draft, utc_now, votes_for_draft
from blogbot.models import Draft, DraftStatus


def _insert_generated_drafts(conn, run_id, sample_angle, n: int) -> list[int]:
    ids = []
    for i in range(n):
        now = utc_now()
        d = Draft(
            run_id=run_id,
            angle_id=sample_angle.id,
            title=f"Draft {i}",
            slug=f"draft-{i}",
            markdown="# D\n\nbody",
            created_at=now,
            updated_at=now,
        )
        ids.append(insert_draft(conn, d))
    return ids


# ---------------------------------------------------------------------------
# Selection math
# ---------------------------------------------------------------------------

class _StubPanel:
    def complete_json(self, system, user, schema_hint, *, max_tokens=256):
        return {"score": 7.0, "critique": "ok"}


def _run_with_stub(conn, config, n_drafts, run_id, sample_angle):
    import blogbot.agents.panel as _mod
    orig = _mod.get_client
    _mod.get_client = lambda role, cfg, secrets: _StubPanel()
    ids = _insert_generated_drafts(conn, run_id, sample_angle, n_drafts)
    try:
        report = run_panel(conn, config, load_secrets(), run_id)
    finally:
        _mod.get_client = orig
    return report, ids


def test_selection_6_drafts_k2(conn, run_id, sample_angle):
    config = load_config()
    config.run.panel_top_fraction = 0.30
    config.run.max_publishes_per_run = 10
    report, _ = _run_with_stub(conn, config, 6, run_id, sample_angle)
    expected_k = max(1, min(math.ceil(6 * 0.30), 10))
    assert report.k == expected_k
    selected = [v for v in report.verdicts if v.verdict == "selected"]
    assert len(selected) == expected_k


def test_selection_1_draft_k1(conn, run_id, sample_angle):
    config = load_config()
    config.run.panel_top_fraction = 0.30
    config.run.max_publishes_per_run = 10
    report, _ = _run_with_stub(conn, config, 1, run_id, sample_angle)
    assert report.k == 1


def test_selection_capped_by_max_publishes(conn, run_id, sample_angle):
    config = load_config()
    config.run.panel_top_fraction = 1.0  # all pass fraction
    config.run.max_publishes_per_run = 2
    report, _ = _run_with_stub(conn, config, 6, run_id, sample_angle)
    assert report.k == 2


# ---------------------------------------------------------------------------
# Vote failure → neutral 5.0
# ---------------------------------------------------------------------------

class _FailPanel:
    def complete_json(self, system, user, schema_hint, *, max_tokens=256):
        raise Exception("simulated failure")


def test_vote_failure_records_neutral(conn, run_id, sample_angle):
    import blogbot.agents.panel as _mod
    orig = _mod.get_client
    _mod.get_client = lambda role, cfg, secrets: _FailPanel()

    _insert_generated_drafts(conn, run_id, sample_angle, 1)
    config = load_config()
    draft_id = conn.execute(
        "SELECT id FROM drafts WHERE run_id=? ORDER BY id DESC LIMIT 1", (run_id,)
    ).fetchone()[0]

    run_panel(conn, config, load_secrets(), run_id)
    _mod.get_client = orig

    votes = votes_for_draft(conn, draft_id)
    neutral = [v for v in votes if v.score == 5.0 and "[vote failed:" in v.critique]
    assert len(neutral) == len(votes)
