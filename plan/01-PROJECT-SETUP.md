# Stage 01 — Project Setup

## Objective
Create repo skeleton, virtual environment, dependency manifest, config file, and secrets scheme. No agent logic yet.

## Tasks

### 1. Verify environment
Run `python --version`. Require 3.11 or newer.
`ASK USER` if Python < 3.11 or not found: ask which interpreter to use.

### 2. Git init
In `E:\localai\blogbotbob`:
```
git init -b main
```

### 3. Create directory tree
Create exactly the layout in `00-MASTER-PLAN.md` §Directory layout (empty `__init__.py` files included; `tests/` empty for now; `data/` created with a `.gitkeep`).

### 4. `.gitignore` (exact content)
```
.venv/
__pycache__/
*.pyc
.env
data/
!data/.gitkeep
dist/
*.egg-info/
.pytest_cache/
```

### 5. `pyproject.toml`
Project name `blogbotbob`, version `0.1.0`, `requires-python = ">=3.11"`.
Dependencies (pin minimum versions, do not pin exact):
- `pydantic>=2.7`
- `pyyaml>=6.0`
- `python-dotenv>=1.0`
- `httpx>=0.27`
- `feedparser>=6.0`
- `praw>=7.7`
- `anthropic>=0.40`
- `python-frontmatter>=1.1`
- `typer>=0.12`

Dev dependencies (optional group `dev`): `pytest>=8.0`, `pytest-httpx>=0.30`.

Entry point:
```toml
[project.scripts]
blogbot = "blogbot.cli:app"
```
Build backend: setuptools, `src` layout (`package-dir = {"" = "src"}`).

### 6. Virtual env + install
```
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
```

### 7. `config.yaml` (exact starter content — values are defaults, not secrets)
```yaml
run:
  max_publishes_per_run: 2
  panel_top_fraction: 0.30

sources:
  rss:
    enabled: true
    feeds: []          # user adds feed URLs
    max_items_per_feed: 20
  hackernews:
    enabled: true
    max_items: 30
  reddit:
    enabled: false     # requires creds in .env
    subreddits: []
    max_items_per_sub: 20
  linkedin:
    enabled: false     # experimental; requires browser automation
  twitter:
    enabled: false     # requires paid API creds

llm:
  ollama:
    base_url: "http://localhost:11434"
    model_analysis: ""   # user supplies at ASK USER checkpoint
    model_panel: ""
  anthropic:
    model_draft: "claude-sonnet-4-6"
    max_tokens_draft: 4096

panel:
  personas_file: "personas.yaml"
  scores_per_draft: 5    # one score per persona

imagery:
  comfyui:
    base_url: "http://localhost:8188"
    workflow_file: "comfy_workflow.json"
    width: 1200
    height: 630
    timeout_seconds: 300

wordpress:
  base_url: ""           # user supplies; e.g. https://example.com
  default_status: "draft"  # pipeline publishes as WP draft first run; switch to "publish" after verified
  category: "AI"

drafting:
  posts_per_run: 6        # drafts generated per run (before panel cull)
  min_words: 700
  max_words: 1200
```

### 8. `.env.example` (exact content; real `.env` NEVER committed)
```
# Anthropic
ANTHROPIC_API_KEY=

# Reddit (script app at https://www.reddit.com/prefs/apps)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=blogbotbob/0.1

# X / Twitter API v2 (optional)
TWITTER_BEARER_TOKEN=

# LinkedIn (optional, experimental)
LINKEDIN_EMAIL=
LINKEDIN_PASSWORD=

# WordPress Application Password
WP_USERNAME=
WP_APP_PASSWORD=
```

### 9. `src/blogbot/config.py`
Implement:
- `load_config(path: Path = Path("config.yaml")) -> Config` — parse YAML into a Pydantic `Config` model mirroring §7 exactly. Unknown keys: error. Missing keys: use defaults from §7.
- `load_secrets() -> Secrets` — `dotenv` load; Pydantic model with all keys from §8, all optional strings defaulting to `""`.
- Validation helper `require_secret(name: str, value: str) -> str` — raises `MissingSecretError` naming the exact `.env` key when empty.

### 10. `README.md`
Sections: What it does (one paragraph from master plan §What is being built), Quick start (venv install → `blogbot setup` wizard → `blogbot run` — no manual file editing required), Pipeline diagram (ASCII, 7 steps), Configuration table, Security note (creds only in `.env`, written by the wizard, never committed).

### 11. No user input at this stage
`config.yaml` ships with empty feeds/models/URLs exactly as §7 shows. The `blogbot setup` wizard (Stage 11 §0) fills them at first run. Do NOT ask the user for feeds, model names, or any credential now.

Add helper to `config.py` for the wizard to use later:
- `save_config(config: Config, path: Path = Path("config.yaml")) -> None` — dump back to YAML preserving the §7 key order.
- `write_env(updates: dict[str, str], path: Path = Path(".env")) -> None` — create `.env` from `.env.example` template if absent, then set/replace only the given keys, preserving other lines.

### 12. First commit
Run secret scan (13-SCHEDULER-DEPLOY.md §1), then:
```
git add -A && git commit -m "chore: project skeleton, config and secrets scheme"
```

## Acceptance criteria
- [ ] `.venv\Scripts\python -c "import blogbot"` exits 0
- [ ] `.venv\Scripts\blogbot --help` shows Typer help (empty CLI acceptable this stage)
- [ ] `python -c "from blogbot.config import load_config; load_config()"` exits 0
- [ ] `.env` absent from `git status` tracked files; `.env.example` present
- [ ] `git log --oneline` shows 1 commit
