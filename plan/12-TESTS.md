# Stage 12 — Tests

## Objective
Pytest suite covering pure logic and adapter parsing with ALL external services mocked. No test may hit network, Ollama, ComfyUI, Anthropic, or WordPress.

## Layout
```
tests/
├── conftest.py          # tmp_path SQLite conn fixture (init_db), sample Topic/Draft factories
├── test_db.py
├── test_config.py
├── test_llm.py
├── test_sources.py
├── test_panel.py
├── test_generation.py
└── test_wordpress.py
```

## Required cases (minimum)

**test_db.py**
- upsert dedupe (same source+external_id → 1 row)
- update_draft whitelist violation raises ValueError
- status transitions persist; slugify: unicode fold, length cap, collapse dashes

**test_config.py**
- defaults load with minimal yaml; unknown key errors; require_secret raises MissingSecretError naming key

**test_llm.py**
- `extract_json`: fenced / bare / prose-wrapped inputs
- complete_json retry-once-then-LLMError using a stub client returning invalid JSON twice
- router: empty ollama model name → LLMError; DRAFT role without ANTHROPIC_API_KEY → MissingSecretError

**test_sources.py**
- RSS: parse fixture XML (checked-in file under `tests/fixtures/feed.xml`) → correct Topic fields
- HN: mocked httpx (pytest-httpx) JSON → Topics with raw_score
- Reddit source with missing creds → SourceError message names env keys
- scraper continues when one source raises (stub sources, one bad + one good → report has 1 error, topics inserted)

**test_panel.py**
- selection math: 6 drafts, fraction 0.30 → k=2; 1 draft → k=1; cap by max_publishes_per_run
- vote failure path → neutral 5.0 recorded

**test_generation.py**
- frontmatter validation: missing `tags` triggers retry path (stub LLM: bad then good)
- word-count floor triggers retry

**test_setup_wizard.py**
- `write_env` creates from template, replaces only given keys, preserves others
- `save_config` round-trips config.yaml without key loss
- wizard section abort leaves config.yaml byte-identical

**test_wordpress.py** (pytest-httpx)
- verify() 200 → name; 401 → WordPressError containing "Application Password"
- ensure_category found vs created
- create_post payload contains featured_media, category id, tag ids

## Commands
```
.venv\Scripts\pytest -q
```
All green required. Add `pytest.ini_options` to pyproject: `testpaths=["tests"]`.

## Acceptance criteria
- [ ] `pytest -q` exits 0, ≥ 20 tests collected
- [ ] Grep proves no test imports `time.sleep`-based polling against real services (mocks only)
- [ ] Commit: `test: unit suite with mocked externals`
