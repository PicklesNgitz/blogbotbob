# Stage 14 — End-to-End Verification

## Objective
Prove the whole pipeline works on real services, with the user watching. This stage produces no new code — only fixes for what it exposes (each fix commits separately, secret-scan first).

## Checklist (run in order, show user each result)

0. **First-run setup**: user runs `blogbot setup` and completes every section (Anthropic key, Ollama models, sources + feeds, ComfyUI checkpoint, WordPress creds, cadence). This is the FIRST time real credentials enter the system. Wizard summary shows all sections configured.
1. **Health**: `blogbot healthcheck` → both `ok`.
2. **Fresh run**: `blogbot run` → exit 0; summary shows topics > 0, angles ≥ 1, drafts ≥ 1, queued ≥ 1.
3. **DB sanity**: `blogbot status` — no drafts stuck in `generated`/`scored`; any `failed` drafts have non-empty `error_message`.
4. **Queue review with user**: `blogbot queue list`, `queue show` each item. User approves ≥1, rejects ≥0. Exercise `queue edit`/`save` on one draft at least once.
5. **Publish (WP draft mode)**: `blogbot publish` → wp_url printed. User opens wp-admin, checks: title, body renders (headings, lists), featured image attached, category + tags right, excerpt = description.
6. **`ASK USER`**: flip `wordpress.default_status` to `publish`? Only on explicit yes.
7. **Idempotency**: `blogbot publish` again → `Nothing approved to publish.`
8. **Scheduler**: `Start-ScheduledTask "BlogBotBob Weekly"` → `data\scheduler.log` gains a full run; queue has new items.
9. **Cold-start resilience**: stop Ollama, run `blogbot run` → clean `PipelineHalt`-style failure message (not traceback spam), exit 1, restart Ollama.
10. **Tests + CI**: `pytest -q` green locally; latest GitHub Actions run green.
11. **Public repo hygiene**: browse repo on github.com as logged-out user — no `.env`, no `data/`, README renders with pipeline diagram.

## Sign-off
Present the user a final summary table: stage, criteria, pass/fail. All pass → project complete, tag `v0.1.0`:
```
git tag v0.1.0 && git push --tags
```

## Known v1 limitations (record in README, do not fix now)
- LinkedIn source is a stub (browser automation deferred).
- X/Twitter raw_score always 0 (engagement metrics need extra API scope).
- Queue is CLI-only; no notifications when a scheduled run enqueues drafts.
- Single WordPress target; no multi-site.
