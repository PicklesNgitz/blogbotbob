# BlogBotBob — Multi-Agent Blog Content Pipeline — MASTER PLAN

## What is being built

End-to-end editorial automation running locally on the owner's Windows PC:

1. **Scraper agent** pulls trending topics from configurable sources (RSS, Hacker News, Reddit, LinkedIn, X).
2. **Analysis agent** dedupes, clusters, and synthesizes prioritized content angles.
3. **Generation agent** drafts full blog posts from the top angles.
4. **Audience panel** (simulated persona agents) scores each draft; top 30% survive.
5. **Image agent** generates a header image per surviving draft via local ComfyUI/SDXL.
6. **Approval queue** — human approves/rejects each candidate via CLI.
7. **Publisher** posts approved drafts (with image) to WordPress via REST API.

## Locked decisions (do NOT revisit; do NOT substitute)

| Decision | Value |
|---|---|
| Language | Python 3.11+ |
| Topic sources | RSS, Hacker News, Reddit, LinkedIn, X — each individually enable/disable via config; disabled sources must not block a run |
| Credentials | `.env` file only, gitignored. NEVER in code, config.yaml, or git history |
| LLM backend | Hybrid: Ollama (local) for scraping-support/analysis/panel scoring; Anthropic Claude API for final draft generation |
| Anthropic model | `claude-sonnet-4-6` for drafts (config-overridable) |
| Publish target | WordPress REST API with Application Password auth |
| Imagery | Local ComfyUI API, SDXL workflow |
| Runtime | Windows Task Scheduler, weekly by default |
| Approval | Mandatory human approval queue before any publish |
| Cadence | Configurable; defaults: 1 run/week, max 2 publishes per run |
| Repo | Public GitHub repo `blogbotbob` under `PicklesNgitz` |
| Storage | Single SQLite database `data/blogbot.db` |
| Selection rule | Top 30% of scored drafts (rounded up, minimum 1) enter approval queue |
| Build-time inputs | NONE. The build requires zero credentials, API keys, feed lists, model names, or service URLs. All runtime configuration is collected from the user by the `blogbot setup` first-run wizard (Stage 11 §0) after installation. Build stages verify against mocks/stubs; real services are touched only in Stage 14 with the user present |

## Executor rules (binding)

1. Execute stages in order. Do not start a stage before the previous stage's acceptance criteria all pass.
2. **No assumptions. No silent decisions.** If anything is ambiguous, missing, or fails in a way a stage file does not cover: STOP and ask the user. Every stage file marks explicit `ASK USER` checkpoints — these are mandatory interactive stops.
3. Never invent config values, URLs, ports, model names, or credentials. Ship empty/default placeholders; the `blogbot setup` wizard collects real values from the user at first run. Do not ask the user for credentials or config values during build stages 01–13 — only Stage 14 (verification, user present) uses real values.
4. Never commit secrets. Before every `git commit`: run the secret-scan check defined in `13-SCHEDULER-DEPLOY.md` §1.
5. Each stage ends with its acceptance criteria run and shown to the user.
6. Keep context small: read only the current stage file plus files it names. Do not re-read the whole plan.
7. Code style: PEP 8, type hints on all public functions, no dead code, no speculative abstractions beyond what stage files specify.

## Stage index

| File | Stage |
|---|---|
| 01-PROJECT-SETUP.md | Repo skeleton, venv, config + secrets scheme |
| 02-DATA-MODELS.md | SQLite schema + Pydantic models |
| 03-LLM-LAYER.md | Ollama + Anthropic clients, role routing |
| 04-SCRAPER-AGENT.md | Source adapters + scraper agent |
| 05-ANALYSIS-AGENT.md | Dedupe/cluster/angle synthesis |
| 06-GENERATION-AGENT.md | Draft generation via Claude |
| 07-AUDIENCE-PANEL.md | Persona panel scoring + top-30% selection |
| 08-IMAGE-AGENT.md | ComfyUI SDXL header image generation |
| 09-APPROVAL-QUEUE.md | CLI review queue |
| 10-PUBLISHER.md | WordPress REST publishing |
| 11-PIPELINE-CLI.md | Orchestrator CLI wiring all stages |
| 12-TESTS.md | Pytest suite, mocked externals |
| 13-SCHEDULER-DEPLOY.md | GitHub repo, secret hygiene, Task Scheduler |
| 14-VERIFY.md | End-to-end acceptance run |

## Directory layout (final)

```
blogbotbob/
├── plan/                  # these files
├── src/blogbot/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── ollama_client.py
│   │   ├── anthropic_client.py
│   │   └── router.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── scraper.py
│   │   ├── analysis.py
│   │   ├── generation.py
│   │   ├── panel.py
│   │   └── imagery.py
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── rss.py
│   │   ├── hackernews.py
│   │   ├── reddit.py
│   │   ├── linkedin.py
│   │   └── twitter.py
│   ├── publish/
│   │   ├── __init__.py
│   │   └── wordpress.py
│   └── cli.py
├── tests/
├── data/                  # gitignored: blogbot.db, images/
├── config.yaml
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```
