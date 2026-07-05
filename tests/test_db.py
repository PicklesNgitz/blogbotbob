"""test_db.py — DB layer tests."""
import pytest

from blogbot.db import (
    get_draft,
    insert_draft,
    set_topic_status,
    slugify,
    update_draft,
    upsert_topic,
    utc_now,
)
from blogbot.models import Draft, DraftStatus, Topic, TopicStatus


def test_upsert_dedupe(conn, run_id, sample_angle):
    t = Topic(source="rss", external_id="dedup-1", title="Dupe", fetched_at=utc_now())
    id1 = upsert_topic(conn, t)
    id2 = upsert_topic(conn, t)
    assert id1 == id2
    count = conn.execute(
        "SELECT COUNT(*) FROM topics WHERE source='rss' AND external_id='dedup-1'"
    ).fetchone()[0]
    assert count == 1


def test_update_draft_whitelist_violation(conn, sample_draft):
    with pytest.raises(ValueError, match="bad_field"):
        update_draft(conn, sample_draft.id, bad_field="nope")


def test_status_transition_persists(conn, sample_draft):
    update_draft(conn, sample_draft.id, status=DraftStatus.scored.value)
    d = get_draft(conn, sample_draft.id)
    assert d.status == DraftStatus.scored


def test_slugify_unicode():
    assert slugify("Café résumé") == "cafe-resume"


def test_slugify_length_cap():
    long_title = "a" * 100
    assert len(slugify(long_title)) <= 80


def test_slugify_collapse_dashes():
    s = slugify("hello  ---  world")
    assert "--" not in s
    assert s == "hello-world"


def test_slugify_strip_ends():
    s = slugify("  --hello world--  ")
    assert not s.startswith("-")
    assert not s.endswith("-")
