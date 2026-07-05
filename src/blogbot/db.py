from __future__ import annotations

import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from blogbot.models import Angle, Draft, DraftStatus, PanelVote, Run, Topic, TopicStatus

_DRAFT_UPDATABLE = frozenset(
    {
        "title",
        "slug",
        "markdown",
        "status",
        "panel_score",
        "image_path",
        "image_prompt",
        "wp_post_id",
        "wp_url",
        "error_message",
    }
)

_DDL = """
CREATE TABLE IF NOT EXISTS topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  summary TEXT,
  raw_score REAL DEFAULT 0,
  fetched_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  UNIQUE(source, external_id)
);

CREATE TABLE IF NOT EXISTS angles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  title TEXT NOT NULL,
  rationale TEXT NOT NULL,
  priority INTEGER NOT NULL,
  topic_ids TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  angle_id INTEGER NOT NULL REFERENCES angles(id),
  title TEXT NOT NULL,
  slug TEXT NOT NULL,
  markdown TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'generated',
  panel_score REAL,
  image_path TEXT,
  image_prompt TEXT,
  wp_post_id INTEGER,
  wp_url TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS panel_votes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  draft_id INTEGER NOT NULL REFERENCES drafts(id),
  persona TEXT NOT NULL,
  score REAL NOT NULL,
  critique TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  stage_reached TEXT,
  notes TEXT
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    lower = ascii_str.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lower)
    slug = slug.strip("-")
    return slug[:80]


def get_conn(db_path: Path = Path("data/blogbot.db")) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)
    conn.commit()


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

def upsert_topic(conn: sqlite3.Connection, t: Topic) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO topics
          (source, external_id, title, url, summary, raw_score, fetched_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (t.source, t.external_id, t.title, t.url, t.summary, t.raw_score, t.fetched_at, t.status.value),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM topics WHERE source = ? AND external_id = ?",
        (t.source, t.external_id),
    ).fetchone()
    return row["id"]


def topics_by_status(conn: sqlite3.Connection, status: TopicStatus) -> list[Topic]:
    rows = conn.execute(
        "SELECT * FROM topics WHERE status = ?", (status.value,)
    ).fetchall()
    return [Topic(**dict(r)) for r in rows]


def set_topic_status(conn: sqlite3.Connection, ids: list[int], status: TopicStatus) -> None:
    conn.executemany(
        "UPDATE topics SET status = ? WHERE id = ?",
        [(status.value, i) for i in ids],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Angles
# ---------------------------------------------------------------------------

def insert_angle(conn: sqlite3.Connection, a: Angle) -> int:
    cur = conn.execute(
        """
        INSERT INTO angles (run_id, title, rationale, priority, topic_ids, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (a.run_id, a.title, a.rationale, a.priority, a.topic_ids, a.created_at),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def angles_for_run(conn: sqlite3.Connection, run_id: str) -> list[Angle]:
    rows = conn.execute(
        "SELECT * FROM angles WHERE run_id = ? ORDER BY priority", (run_id,)
    ).fetchall()
    return [Angle(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

def insert_draft(conn: sqlite3.Connection, d: Draft) -> int:
    cur = conn.execute(
        """
        INSERT INTO drafts
          (run_id, angle_id, title, slug, markdown, status,
           panel_score, image_path, image_prompt, wp_post_id, wp_url,
           error_message, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            d.run_id, d.angle_id, d.title, d.slug, d.markdown, d.status.value,
            d.panel_score, d.image_path, d.image_prompt, d.wp_post_id, d.wp_url,
            d.error_message, d.created_at, d.updated_at,
        ),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def update_draft(conn: sqlite3.Connection, draft_id: int, **fields) -> None:
    bad = set(fields) - _DRAFT_UPDATABLE
    if bad:
        raise ValueError(f"Non-whitelisted draft fields: {bad}")
    if not fields:
        return
    fields["updated_at"] = utc_now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [draft_id]
    conn.execute(f"UPDATE drafts SET {set_clause} WHERE id = ?", values)
    conn.commit()


def drafts_by_status(
    conn: sqlite3.Connection,
    status: DraftStatus,
    run_id: Optional[str] = None,
) -> list[Draft]:
    if run_id:
        rows = conn.execute(
            "SELECT * FROM drafts WHERE status = ? AND run_id = ?", (status.value, run_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM drafts WHERE status = ?", (status.value,)
        ).fetchall()
    return [Draft(**dict(r)) for r in rows]


def get_draft(conn: sqlite3.Connection, draft_id: int) -> Draft:
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        raise ValueError(f"Draft {draft_id} not found")
    return Draft(**dict(row))


# ---------------------------------------------------------------------------
# Panel votes
# ---------------------------------------------------------------------------

def insert_vote(conn: sqlite3.Connection, v: PanelVote) -> int:
    cur = conn.execute(
        """
        INSERT INTO panel_votes (draft_id, persona, score, critique, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (v.draft_id, v.persona, v.score, v.critique, v.created_at),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def votes_for_draft(conn: sqlite3.Connection, draft_id: int) -> list[PanelVote]:
    rows = conn.execute(
        "SELECT * FROM panel_votes WHERE draft_id = ?", (draft_id,)
    ).fetchall()
    return [PanelVote(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def start_run(conn: sqlite3.Connection) -> str:
    run_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO runs (id, started_at) VALUES (?, ?)",
        (run_id, utc_now()),
    )
    conn.commit()
    return run_id


def finish_run(conn: sqlite3.Connection, run_id: str, stage_reached: str, notes: str = "") -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, stage_reached = ?, notes = ? WHERE id = ?",
        (utc_now(), stage_reached, notes, run_id),
    )
    conn.commit()
