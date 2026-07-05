"""Shared fixtures for the test suite."""
import json
import sqlite3

import pytest

from blogbot.db import get_conn, init_db, insert_angle, insert_draft, start_run, upsert_topic, utc_now
from blogbot.models import Angle, Draft, DraftStatus, Topic


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    c = get_conn(db)
    init_db(c)
    return c


@pytest.fixture
def run_id(conn) -> str:
    return start_run(conn)


@pytest.fixture
def sample_topic(conn) -> Topic:
    t = Topic(
        source="hackernews",
        external_id="fix-001",
        title="Sample Topic",
        url="https://example.com/1",
        summary="A summary.",
        raw_score=42.0,
        fetched_at=utc_now(),
    )
    tid = upsert_topic(conn, t)
    t.id = tid
    return t


@pytest.fixture
def sample_angle(conn, run_id, sample_topic) -> Angle:
    a = Angle(
        run_id=run_id,
        title="Sample Angle",
        rationale="Rationale",
        priority=1,
        topic_ids=json.dumps([sample_topic.id]),
        created_at=utc_now(),
    )
    aid = insert_angle(conn, a)
    a.id = aid
    return a


GOOD_MARKDOWN = """\
---
title: Test Post
description: A test description for the blog post.
tags: [ai, test]
---

## Introduction

This is the body text of the blog post.

## What to do with this

Take action based on what you learned.
""" + "word " * 600


@pytest.fixture
def sample_draft(conn, run_id, sample_angle) -> Draft:
    now = utc_now()
    d = Draft(
        run_id=run_id,
        angle_id=sample_angle.id,
        title="Test Post",
        slug="test-post",
        markdown=GOOD_MARKDOWN,
        created_at=now,
        updated_at=now,
    )
    did = insert_draft(conn, d)
    d.id = did
    return d
