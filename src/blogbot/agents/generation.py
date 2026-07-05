from __future__ import annotations

import json
import logging
import sqlite3

import frontmatter

from blogbot.agents import PipelineHalt
from blogbot.config import Config, Secrets
from blogbot.db import angles_for_run, insert_draft, slugify, utc_now
from blogbot.llm.base import LLMError
from blogbot.llm.router import Role, get_client
from blogbot.models import Draft

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a senior technology writer for a blog read by small and medium "
    "business owners and operators evaluating practical AI adoption. Voice: "
    "authoritative, concrete, plain-spoken; no hype, no filler phrases, no "
    '"in today\'s fast-paced world" openings. Use specific examples. American '
    "English."
)

_REQUIRED_FM_KEYS = {"title", "description", "tags"}


def _build_user_prompt(
    angle_title: str,
    angle_rationale: str,
    topic_lines: str,
    min_words: int,
    max_words: int,
) -> str:
    return (
        "Write a complete blog post.\n\n"
        f"Angle: {angle_title}\n"
        f"Why this angle matters: {angle_rationale}\n"
        f"Source material (context only, do not quote verbatim):\n{topic_lines}\n\n"
        "Requirements:\n"
        f"- {min_words}-{max_words} words.\n"
        "- Start with YAML frontmatter delimited by --- lines containing exactly:\n"
        "  title, description (max 155 chars), tags (3-5 lowercase strings).\n"
        "- After frontmatter: markdown body. H2/H3 sections. One actionable\n"
        '  takeaway section at the end titled "What to do with this".\n'
        "- No H1 in body (title lives in frontmatter).\n"
        "Return ONLY the frontmatter + markdown, nothing else."
    )


def _word_count(text: str) -> int:
    return len(text.split())


def _parse_and_validate(raw_text: str, min_words: int) -> tuple[frontmatter.Post | None, list[str]]:
    """Parse frontmatter. Return (post, missing_keys). Returns (None, []) on parse error."""
    try:
        post = frontmatter.loads(raw_text)
    except Exception as e:
        logger.debug("frontmatter parse error: %s", e)
        return None, ["frontmatter could not be parsed"]

    missing = [k for k in _REQUIRED_FM_KEYS if k not in post.metadata]
    if missing:
        return post, missing

    body_words = _word_count(post.content)
    if body_words < int(min_words * 0.7):
        return post, [f"body too short ({body_words} words, need ≥{int(min_words*0.7)})"]

    return post, []


def run_generation(
    conn: sqlite3.Connection,
    config: Config,
    secrets: Secrets,
    run_id: str,
) -> list[int]:
    angles = angles_for_run(conn, run_id)
    if not angles:
        raise PipelineHalt("no angles for this run; run analyze first")

    client = get_client(Role.DRAFT, config, secrets)
    min_words = config.drafting.min_words
    max_words = config.drafting.max_words
    max_tokens = config.llm.anthropic.max_tokens_draft

    # Collect topic titles for context lines per angle
    draft_ids: list[int] = []
    total_calls = 0

    for angle in angles:
        topic_ids: list[int] = json.loads(angle.topic_ids)
        topic_rows = []
        if topic_ids:
            placeholders = ",".join("?" * len(topic_ids))
            topic_rows = conn.execute(
                f"SELECT title, url FROM topics WHERE id IN ({placeholders})",
                topic_ids,
            ).fetchall()
        topic_lines = "\n".join(
            f"- {row['title']}" + (f" ({row['url']})" if row["url"] else "")
            for row in topic_rows
        )

        user_prompt = _build_user_prompt(
            angle.title, angle.rationale, topic_lines, min_words, max_words
        )

        # First attempt
        try:
            raw = client.complete(_SYSTEM, user_prompt, max_tokens=max_tokens)
            total_calls += 1
        except LLMError as e:
            logger.warning("generation: angle %r failed: %s", angle.title, e)
            continue

        post, issues = _parse_and_validate(raw, min_words)

        if issues:
            # Single retry
            retry_prompt = (
                user_prompt + f"\n\nYour previous output had issues: {'; '.join(issues)}. Regenerate fully."
            )
            try:
                raw = client.complete(_SYSTEM, retry_prompt, max_tokens=max_tokens)
                total_calls += 1
            except LLMError as e:
                logger.warning("generation: angle %r retry failed: %s", angle.title, e)
                continue
            post, issues = _parse_and_validate(raw, min_words)
            if issues:
                logger.warning("generation: angle %r skipped after retry: %s", angle.title, issues)
                continue

        title = str(post.metadata.get("title", angle.title))
        slug = slugify(title)
        now = utc_now()
        draft = Draft(
            run_id=run_id,
            angle_id=angle.id,  # type: ignore[arg-type]
            title=title,
            slug=slug,
            markdown=raw,
            created_at=now,
            updated_at=now,
        )
        draft_id = insert_draft(conn, draft)
        draft_ids.append(draft_id)
        words = _word_count(post.content)
        logger.info("generation: drafted %r (%d words)", title, words)

    logger.info("generation: Anthropic calls: %d", total_calls)
    if not draft_ids:
        raise PipelineHalt("generation produced no drafts")

    return draft_ids
