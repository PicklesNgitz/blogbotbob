# Stage 02 — Data Models & SQLite

## Objective
Single SQLite DB with full pipeline state. All later stages read/write ONLY through `db.py` functions defined here.

## Files
- `src/blogbot/models.py` — Pydantic models
- `src/blogbot/db.py` — connection, schema creation, CRUD

## 1. Status lifecycle (single source of truth)

Draft status enum (`DraftStatus`, `str, Enum`):
```
generated → scored → selected → image_ready → pending_approval → approved → published
                                    ↓                                ↓
                                 rejected  (panel cull)          rejected (human)
```
Additionally `failed` — any stage error stamps the draft `failed` with `error_message`.

Topic status enum (`TopicStatus`): `new → analyzed → drafted` plus `discarded`.

## 2. Schema (DDL — create verbatim in `db.py:init_db()`)

```sql
CREATE TABLE IF NOT EXISTS topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,              -- rss|hackernews|reddit|linkedin|twitter
  external_id TEXT NOT NULL,         -- source-native id/url for dedupe
  title TEXT NOT NULL,
  url TEXT,
  summary TEXT,
  raw_score REAL DEFAULT 0,          -- source-native popularity signal
  fetched_at TEXT NOT NULL,          -- ISO 8601 UTC
  status TEXT NOT NULL DEFAULT 'new',
  UNIQUE(source, external_id)
);

CREATE TABLE IF NOT EXISTS angles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  title TEXT NOT NULL,
  rationale TEXT NOT NULL,
  priority INTEGER NOT NULL,         -- 1 = highest
  topic_ids TEXT NOT NULL,           -- JSON array of topics.id
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  angle_id INTEGER NOT NULL REFERENCES angles(id),
  title TEXT NOT NULL,
  slug TEXT NOT NULL,
  markdown TEXT NOT NULL,            -- body incl. frontmatter
  status TEXT NOT NULL DEFAULT 'generated',
  panel_score REAL,                  -- mean persona score, 0-10
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
  score REAL NOT NULL,               -- 0-10
  critique TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,               -- uuid4 hex
  started_at TEXT NOT NULL,
  finished_at TEXT,
  stage_reached TEXT,
  notes TEXT
);
```

## 3. `models.py`
Pydantic models mirroring each table 1:1: `Topic`, `Angle`, `Draft`, `PanelVote`, `Run` — field names identical to columns. Enums from §1. All timestamps `str` ISO 8601 UTC produced by helper `utc_now() -> str` in `db.py`.

## 4. `db.py` API (implement exactly these signatures)

```python
def get_conn(db_path: Path = Path("data/blogbot.db")) -> sqlite3.Connection  # row_factory=sqlite3.Row, foreign_keys ON
def init_db(conn) -> None
def utc_now() -> str

# topics
def upsert_topic(conn, t: Topic) -> int          # INSERT OR IGNORE on (source, external_id); return existing id if dupe
def topics_by_status(conn, status: TopicStatus) -> list[Topic]
def set_topic_status(conn, ids: list[int], status: TopicStatus) -> None

# angles
def insert_angle(conn, a: Angle) -> int
def angles_for_run(conn, run_id: str) -> list[Angle]

# drafts
def insert_draft(conn, d: Draft) -> int
def update_draft(conn, draft_id: int, **fields) -> None   # whitelist updatable columns; always bumps updated_at
def drafts_by_status(conn, status: DraftStatus, run_id: str | None = None) -> list[Draft]
def get_draft(conn, draft_id: int) -> Draft

# panel
def insert_vote(conn, v: PanelVote) -> int
def votes_for_draft(conn, draft_id: int) -> list[PanelVote]

# runs
def start_run(conn) -> str
def finish_run(conn, run_id: str, stage_reached: str, notes: str = "") -> None
```

`update_draft` whitelist: `title, slug, markdown, status, panel_score, image_path, image_prompt, wp_post_id, wp_url, error_message`. Any other kwarg: raise `ValueError`.

## 5. Slug rule
`slugify(title: str) -> str` in `db.py`: lowercase, ASCII-fold, non-alphanumeric → `-`, collapse repeats, strip ends, max 80 chars.

## Acceptance criteria
- [ ] `python -c "from blogbot.db import get_conn, init_db; c=get_conn(); init_db(c)"` creates `data/blogbot.db` with all 5 tables (`.tables` check via sqlite3 CLI or Python)
- [ ] Round-trip test: insert topic → upsert same topic again → count == 1
- [ ] `update_draft` with a non-whitelisted kwarg raises `ValueError`
- [ ] Commit: `feat: sqlite schema and data access layer`
