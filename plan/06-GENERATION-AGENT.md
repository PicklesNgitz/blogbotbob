# Stage 06 — Generation Agent (Claude drafts)

## Objective
One full blog post per angle via Anthropic DRAFT role. Output = markdown with YAML frontmatter, stored as `Draft` rows, status `generated`.

## File
`src/blogbot/agents/generation.py`

## 1. Entry point

```python
def run_generation(conn, config: Config, secrets: Secrets, run_id: str) -> list[int]  # draft ids
```
- Load `angles_for_run(run_id)` ordered by priority. For each angle: one `complete` call (NOT complete_json — body is prose), role DRAFT, `max_tokens=config.llm.anthropic.max_tokens_draft`.
- Per-angle failure (LLMError): log, skip angle, continue. Zero drafts produced → `PipelineHalt`.

## 2. Prompt (verbatim skeleton)

System:
```
You are a senior technology writer for a blog read by small and medium
business owners and operators evaluating practical AI adoption. Voice:
authoritative, concrete, plain-spoken; no hype, no filler phrases, no
"in today's fast-paced world" openings. Use specific examples. American
English.
```

User:
```
Write a complete blog post.

Angle: {angle.title}
Why this angle matters: {angle.rationale}
Source material (context only, do not quote verbatim):
{topic_lines_for_angle}

Requirements:
- {min_words}-{max_words} words.
- Start with YAML frontmatter delimited by --- lines containing exactly:
  title, description (max 155 chars), tags (3-5 lowercase strings).
- After frontmatter: markdown body. H2/H3 sections. One actionable
  takeaway section at the end titled "What to do with this".
- No H1 in body (title lives in frontmatter).
Return ONLY the frontmatter + markdown, nothing else.
```

## 3. Post-processing per draft
- Parse with `python-frontmatter`. Required keys `title`, `description`, `tags` — missing key → ONE retry appending `Your previous output was missing frontmatter key(s): {keys}. Regenerate fully.`; still bad → skip angle, log.
- Word count check: body < `min_words*0.7` → same single-retry policy.
- `slug = slugify(frontmatter title)`.
- Insert draft: full original text (frontmatter incl.) in `markdown`, status `generated`.

## 4. CLI
`blogbot generate --run-id <id>` (defaults to latest run) — prints per-angle result: `drafted "<title>" (1,043 words)` or skip reason.

## 5. Cost note (print, do not act)
After generation print: `Anthropic calls: {n}, est. input+output tokens: {sum}` using SDK usage fields.

## Acceptance criteria (build-time: stub LLM, no API key required)
- [ ] Unit test: `run_generation` with stub DRAFT client returning fixture markdown produces drafts with valid frontmatter; missing-frontmatter fixture triggers single retry then skip
- [ ] `blogbot generate` on unconfigured install (no ANTHROPIC_API_KEY) exits 1 with `run: blogbot setup` guidance, no traceback
- [ ] Real-Claude end-to-end run deferred to Stage 14
- [ ] Commit: `feat: generation agent drafts posts via Claude`
