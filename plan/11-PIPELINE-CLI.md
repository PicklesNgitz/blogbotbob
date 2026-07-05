# Stage 11 — Orchestrator CLI + First-Run Setup Wizard

## Objective
`blogbot setup` interactive wizard collects ALL runtime configuration post-install. Single `blogbot run` command chains scrape → analyze → generate → panel → imagery → enqueue. Publish stays a separate human-triggered command (after queue approval). Logging + run bookkeeping.

## Files
`src/blogbot/cli.py` (extend), `src/blogbot/setup_wizard.py`

## 0. `blogbot setup` — first-run wizard (`setup_wizard.py`)

Interactive prompts via `typer.prompt`/`typer.confirm`. Each section: show current value if set, Enter keeps it (re-runnable, idempotent). Secrets prompted with `hide_input=True`. Writes via `save_config` / `write_env` (Stage 01 §11). NOTHING is written until that section validates.

Sections in order:

1. **Anthropic** — prompt `ANTHROPIC_API_KEY`. Validate: 1-token ping on `llm.anthropic.model_draft`. 401/invalid → show error, re-prompt (max 3, then skip with warning).
2. **Ollama** — prompt base URL (default kept). GET `/api/tags`; unreachable → advise starting Ollama, offer retry/skip. List installed models; user picks `model_analysis` and `model_panel` by number.
3. **Sources** — for each of rss/hackernews/reddit/twitter ask enable? (linkedin: show "not available in v1", keep disabled).
   - rss: loop-prompt feed URLs until blank line; each URL fetch-validated with feedparser (warn on parse failure, allow keep/discard).
   - reddit: prompt subreddits (comma list) + `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`; validate with a 1-item PRAW fetch.
   - twitter: prompt `TWITTER_BEARER_TOKEN` + search query; validate with 1 API call.
4. **ComfyUI** — prompt base URL. GET `/object_info`; list `CheckpointLoaderSimple` checkpoints; user picks → `imagery.comfyui.checkpoint`. Unreachable → advise, retry/skip.
5. **WordPress** — prompt site URL, `WP_USERNAME`, `WP_APP_PASSWORD` (hidden). `WPClient.verify()`; 401 → show WP Application Password instructions, re-prompt. Prompt category (default `AI`).
6. **Cadence** — confirm `max_publishes_per_run` and `posts_per_run` defaults or new values.

Finish: print config summary table (secrets masked to last 4 chars) + `blogbot healthcheck` result. Skipped sections listed with the command to finish later (`blogbot setup` again).

## 0b. Unconfigured guard
`blogbot run|scrape|analyze|generate|panel|imagery|publish`: before executing, check the specific config/secrets that command needs (each stage file defines its `PipelineHalt` message). All these messages end with `— run: blogbot setup`. `blogbot setup` and `blogbot healthcheck` always runnable.

## 1. `blogbot run`
Sequence (each step logs start/finish and counts):
1. `init_db`, `start_run` → run_id.
2. `run_scraper` — if ALL enabled sources errored → finish_run(stage_reached="scrape"), exit 1.
3. `run_analysis`
4. `run_generation`
5. `run_panel`
6. `run_imagery`
7. Enqueue: `image_ready` → `pending_approval` (Stage 09 §1).
8. `finish_run(stage_reached="enqueued", notes=summary)`.
9. Print final summary block:
```
Run {run_id} complete.
topics: {n} new | angles: {n} | drafts: {n} | selected: {k} | queued: {k}
Next: blogbot queue list
```
`PipelineHalt` anywhere → finish_run with reached stage, print message, exit 1. Unexpected exception → same + full traceback to log file.

## 2. Logging
- `logging` stdlib. Console INFO; file handler `data/blogbot.log` DEBUG, rotating (`RotatingFileHandler`, 1 MB × 3).
- Configure once in `cli.py` callback. Every agent module uses `logging.getLogger(__name__)` — retrofit any `print` in agents to logger now.

## 3. Full command surface (final)
```
blogbot setup         # first-run wizard, re-runnable
blogbot healthcheck
blogbot run
blogbot scrape | analyze | generate | panel | imagery   # stage-by-stage debugging
blogbot queue list|show|approve|reject|edit|save
blogbot publish
blogbot status        # NEW: counts per draft status + last 3 runs table
```
Implement `blogbot status` (plain SELECT group-by).

## 4. Build-time verification
No real services. Real end-to-end run happens in Stage 14 after the user runs `blogbot setup`.

## Acceptance criteria (build-time)
- [ ] `blogbot run` on unconfigured install exits 1 with `run: blogbot setup` message at the first gated stage, no traceback
- [ ] `blogbot setup --help` and all wizard prompts reachable (walk wizard until first validation, Ctrl-C out — no config corruption: config.yaml unchanged after abort)
- [ ] `blogbot status` shows sane counts on empty DB
- [ ] `data/blogbot.log` created with DEBUG lines
- [ ] Commit: `feat: setup wizard, orchestrator, status command`
