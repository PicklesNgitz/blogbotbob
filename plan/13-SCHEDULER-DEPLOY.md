# Stage 13 — GitHub Deploy + Task Scheduler

## Objective
Public repo `PicklesNgitz/blogbotbob` on GitHub with zero secrets; weekly scheduled run on the owner's PC.

## 1. Secret scan (mandatory before EVERY commit, all stages)
Run from repo root:
```
git grep -nE "(sk-ant-|AKIA[0-9A-Z]{16}|ANTHROPIC_API_KEY=..+|APP_PASSWORD=..+|CLIENT_SECRET=..+|BEARER_TOKEN=..+)" -- ':!plan/*' ':!.env.example'
```
Any hit → STOP, remove, never commit. Also verify: `git status --porcelain | grep -F ".env"` returns only `.env.example` if anything.

## 2. Pre-push audit (once, before first push — repo is PUBLIC)
- `git log -p | grep -iE "api_key|password|secret|token" | grep -v -E "(example|require_secret|MissingSecret|APP_PASSWORD$|_KEY$|config|test)"` — review every hit manually.
- Confirm `.env` never appears in `git log --all --diff-filter=A --name-only`.
- `ASK USER`: show audit results, get explicit go-ahead to push public.

## 3. Create repo + push
GitHub CLI if available (`gh --version`), else ask user to create empty repo in UI.
```
gh repo create PicklesNgitz/blogbotbob --public --source . --push
```
or
```
git remote add origin https://github.com/PicklesNgitz/blogbotbob.git
git push -u origin main
```
Repo description: `Multi-agent blog content pipeline — scrape → analyze → draft (Claude) → persona-panel scoring → ComfyUI imagery → human approval → WordPress publish.`

## 4. CI (lightweight)
`.github/workflows/test.yml`: on push/PR — checkout, setup-python 3.11, `pip install -e .[dev]`, `pytest -q`. Tests are fully mocked (Stage 12) so CI needs no secrets. NEVER add repo secrets for runtime creds; runtime is local-only.

## 5. Task Scheduler (weekly run)
Create `scripts/run_pipeline.bat`:
```bat
@echo off
cd /d E:\localai\blogbotbob
call .venv\Scripts\activate.bat
blogbot run >> data\scheduler.log 2>&1
```
Register (PowerShell, run as the user, NOT elevated unless required):
```powershell
$action = New-ScheduledTaskAction -Execute "E:\localai\blogbotbob\scripts\run_pipeline.bat"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 7:00AM
Register-ScheduledTask -TaskName "BlogBotBob Weekly" -Action $action -Trigger $trigger -Description "Weekly blog content pipeline run"
```
`ASK USER` first: confirm day/time (default Monday 07:00) and that Ollama + ComfyUI auto-start on their machine or are running at that hour. If ComfyUI is not always-on, note in README that imagery stage will fail and drafts stay `selected` — re-runnable via `blogbot imagery` later. Verify `run_imagery` tolerates this (it does per Stage 08 §5; confirm).

## 6. README updates
Add: scheduler setup section, queue workflow (`run` happens automatically; human runs `blogbot queue list` + `publish` when notified), CI badge.

## Acceptance criteria
- [ ] Repo public at github.com/PicklesNgitz/blogbotbob, CI green
- [ ] Secret audit log shown to user, user approved push
- [ ] `Get-ScheduledTask "BlogBotBob Weekly"` returns the task; manual `Start-ScheduledTask` run writes to `data\scheduler.log`
- [ ] Commit: `ci: tests workflow; docs: scheduler setup`
