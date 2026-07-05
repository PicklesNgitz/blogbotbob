# Stage 09 — Approval Queue (human gate)

## Objective
Mandatory human review between panel/image and publish. CLI-only in v1. `image_ready` drafts become `pending_approval`; human flips each to `approved` or `rejected`.

## File
Queue logic lives in `src/blogbot/cli.py` (thin) + small helpers in `db.py` already defined. No new agent module.

## 1. Auto-enqueue
At end of imagery stage (Stage 11 orchestrator handles ordering): every draft in `image_ready` → status `pending_approval`.

## 2. CLI commands (Typer sub-app `queue`)

`blogbot queue list`
- Table: id, title, panel_score, created_at, image_path.
- Empty queue → print `Queue empty.` exit 0.

`blogbot queue show <draft_id>`
- Print full markdown body to stdout, image path, panel votes (persona, score, critique one-liner).
- Draft not in `pending_approval` → error message with its actual status, exit 1.

`blogbot queue approve <draft_id>`
- Status → `approved`. Print confirmation.

`blogbot queue reject <draft_id> [--reason TEXT]`
- Status → `rejected`; reason appended to `error_message` as `rejected by user: {reason}`.

`blogbot queue edit <draft_id>`
- Dump markdown to `data/edit-{id}.md`, print the path, instruct user to edit and run `blogbot queue save <draft_id>`.

`blogbot queue save <draft_id>`
- Read `data/edit-{id}.md`, re-validate frontmatter (same rules as Stage 06 §3), overwrite `drafts.markdown`, keep status `pending_approval`, delete temp file.

## 3. Guard
Publisher (Stage 10) refuses any draft not in `approved`. There is no bypass flag. This is the hard safety gate of the pipeline — do not weaken it even if asked by tooling defaults.

## Acceptance criteria
- [ ] Full manual walkthrough: list → show → edit → save → approve one draft; reject another with reason
- [ ] `queue approve` on an id in status `generated` fails with clear message
- [ ] Commit: `feat: human approval queue CLI`
