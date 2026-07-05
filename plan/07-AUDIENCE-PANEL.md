# Stage 07 — Audience Panel (scoring + top-30% selection)

## Objective
Simulated persona panel scores every `generated` draft 0–10 via Ollama PANEL role. Mean score ranks drafts; top 30% (round up, min 1, capped by `max_publishes_per_run`) advance to `selected`, rest `rejected`.

## Files
`src/blogbot/agents/panel.py`, `personas.yaml` (repo root)

## 1. `personas.yaml` (exact starter content; user may edit later)

```yaml
personas:
  - name: skeptical_owner
    profile: "Owner of a 40-person services firm. Time-poor, burned by tech fads, cares only about cost, risk, and payback period."
  - name: ops_manager
    profile: "Operations manager at an SMB. Wants step-by-step practicality, tooling names, and realistic effort estimates."
  - name: it_generalist
    profile: "The one IT person at a small company. Technical, allergic to marketing fluff, checks claims for accuracy."
  - name: marketing_lead
    profile: "SMB marketing lead. Cares about clarity, story, and whether the post is shareable to a non-technical audience."
  - name: finance_controller
    profile: "Controller/CFO type. Judges ROI logic, pricing claims, and whether numbers are credible and sourced."
```

`config.panel.scores_per_draft` must equal persona count; on mismatch → `PipelineHalt` naming both numbers.

## 2. Entry point

```python
def run_panel(conn, config: Config, secrets: Secrets, run_id: str) -> PanelReport
```
Per draft × per persona: one `complete_json` call, role PANEL.

System prompt:
```
You role-play exactly this reader and judge a blog draft strictly from
their perspective. Persona: {profile}
Answer ONLY JSON.
```
User prompt:
```
Draft:
---
{draft.markdown}
---
Score this draft 0-10 for how valuable and credible it is TO YOU.
Be harsh; 8+ means you would share it.
JSON schema: {"score": number, "critique": "one paragraph, max 80 words"}
```

- Clamp score into [0,10]. Persist every vote to `panel_votes`.
- One persona call failing → retry once, then record `score=5.0, critique="[vote failed: {err}]"` (neutral, does not sink or boost).

## 3. Selection
- `panel_score` = mean of persona scores → `update_draft`.
- Rank all scored drafts of this run desc. `k = max(1, ceil(len(drafts) * config.run.panel_top_fraction))`, then `k = min(k, config.run.max_publishes_per_run)`.
- Top k → status `selected`; others → `rejected`.
- `PanelReport`: per draft — title, score, verdict; plus k.

## 4. CLI
`blogbot panel --run-id <id>` — prints ranked score table with verdicts.

## Acceptance criteria (build-time: stub LLM)
- [ ] Unit test: stub PANEL client scoring fixture drafts → `panel_votes` rows == drafts × personas; exactly k `selected`, rest `rejected`; vote-failure path records neutral 5.0
- [ ] Persona count mismatch vs `scores_per_draft` → `PipelineHalt` naming both numbers
- [ ] Real-Ollama run deferred to Stage 14
- [ ] Commit: `feat: audience panel scoring and top-30% selection`
