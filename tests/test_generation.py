"""test_generation.py — generation agent tests."""
import json

import pytest

from blogbot.agents import PipelineHalt
from blogbot.agents.generation import run_generation
from blogbot.config import load_config, load_secrets
from blogbot.db import get_draft, insert_angle, insert_draft, utc_now
from blogbot.models import Angle, Draft

GOOD_MD = """\
---
title: Good Post
description: A good description within 155 characters.
tags: [ai, smb, test]
---

## Intro

Body text here.

## What to do with this

Act on it.
""" + "word " * 700


BAD_MD_MISSING_TAGS = """\
---
title: Missing Tags Post
description: Description here.
---

## Body

Body text.
""" + "word " * 700


class _StubDraftBadThenGood:
    def __init__(self):
        self._calls = 0

    def complete(self, system, user, *, max_tokens=1024, temperature=0.7):
        self._calls += 1
        if self._calls == 1:
            return BAD_MD_MISSING_TAGS  # first: bad frontmatter
        return GOOD_MD  # retry: good


class _StubDraftShortBody:
    def __init__(self):
        self._calls = 0

    def complete(self, system, user, *, max_tokens=1024, temperature=0.7):
        self._calls += 1
        if self._calls == 1:
            return "---\ntitle: T\ndescription: D\ntags: [a]\n---\nshort body"
        return GOOD_MD


def _setup(conn, run_id):
    from blogbot.db import upsert_topic, start_run
    from blogbot.models import Topic
    t = Topic(source="hn", external_id="g1", title="T", fetched_at=utc_now())
    from blogbot.db import upsert_topic
    tid = upsert_topic(conn, t)
    a = Angle(run_id=run_id, title="A", rationale="R", priority=1,
              topic_ids=json.dumps([tid]), created_at=utc_now())
    aid = insert_angle(conn, a)
    return aid


def _patch_and_run(conn, run_id, stub_client):
    import blogbot.agents.generation as _mod
    orig = _mod.get_client
    _mod.get_client = lambda role, cfg, secrets: stub_client
    config = load_config()
    try:
        return run_generation(conn, config, load_secrets(), run_id)
    finally:
        _mod.get_client = orig


def test_missing_tags_triggers_retry(conn, run_id):
    _setup(conn, run_id)
    stub = _StubDraftBadThenGood()
    draft_ids = _patch_and_run(conn, run_id, stub)
    assert len(draft_ids) == 1
    assert stub._calls == 2  # first failed, retry succeeded
    d = get_draft(conn, draft_ids[0])
    import frontmatter
    post = frontmatter.loads(d.markdown)
    assert "tags" in post.metadata


def test_short_body_triggers_retry(conn, run_id):
    _setup(conn, run_id)
    stub = _StubDraftShortBody()
    draft_ids = _patch_and_run(conn, run_id, stub)
    assert len(draft_ids) == 1
    assert stub._calls == 2
