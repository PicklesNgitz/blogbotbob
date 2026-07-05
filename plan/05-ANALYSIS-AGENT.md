# Stage 05 — Analysis Agent

## Objective
Turn raw `new` topics into a prioritized list of content angles using the Ollama ANALYSIS role. Pure LLM+DB step, no network beyond Ollama.

## File
`src/blogbot/agents/analysis.py`

## 1. Entry point

```python
def run_analysis(conn, config: Config, secrets: Secrets, run_id: str) -> list[Angle]
```

Steps:
1. Load topics with status `new`. If < 3 topics → raise `PipelineHalt("not enough topics; run scrape first")` (define `PipelineHalt` in `agents/__init__.py`; CLI catches it and prints message, exit 1).
2. Build topic digest: one line per topic — `[{id}] ({source}, score {raw_score}) {title} — {summary first 200 chars}`. Cap digest at 120 topics; if more, keep highest `raw_score` first, then newest.
3. One `complete_json` call, role ANALYSIS.

## 2. Prompt (verbatim skeleton; digest interpolated)

System:
```
You are an editorial strategist for a technology blog aimed at small and
medium business decision-makers interested in practical AI adoption.
You identify which trending topics are worth writing about and propose
concrete article angles. You answer ONLY with JSON.
```

User:
```
Here are trending items collected today:

{digest}

Propose the {n_angles} best article angles. Rules:
- Each angle must cite which item ids inspired it.
- Angles must be practical for SMB readers, not academic.
- No two angles may cover substantially the same story.
- Prioritize: 1 = strongest.

JSON schema:
{"angles": [{"title": str, "rationale": str, "priority": int, "topic_ids": [int]}]}
```

`n_angles` = `config.drafting.posts_per_run`.

## 3. Post-processing
- Validate: every returned `topic_ids` entry exists in the digest ids; drop unknown ids; if an angle ends with zero valid ids, drop the angle and log.
- If fewer than 1 valid angle survives → `PipelineHalt("analysis produced no valid angles")`.
- Insert angles (`run_id`, `created_at=utc_now()`); mark all digested topics `analyzed`.

## 4. CLI
`blogbot analyze` — creates run if none passed, prints angle table (priority, title, topic count).

## Acceptance criteria (build-time: stub LLM, no real Ollama required)
- [ ] Unit test: `run_analysis` with a stub ANALYSIS client returning fixture JSON inserts ≥1 angle, flips topics to `analyzed`, drops angles whose topic_ids are all invalid
- [ ] `blogbot analyze` on unconfigured install (empty `model_analysis`) exits 1 with `run: blogbot setup` guidance, no traceback
- [ ] Real-Ollama end-to-end run deferred to Stage 14
- [ ] Commit: `feat: analysis agent synthesizes prioritized angles`
