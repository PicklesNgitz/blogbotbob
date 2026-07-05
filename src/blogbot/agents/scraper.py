from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from pydantic import BaseModel

from blogbot.config import Config, Secrets
from blogbot.db import upsert_topic
from blogbot.sources.base import Source, SourceError
from blogbot.sources.hackernews import HackerNewsSource
from blogbot.sources.linkedin import LinkedInSource
from blogbot.sources.reddit import RedditSource
from blogbot.sources.rss import RSSSource
from blogbot.sources.twitter import TwitterSource

logger = logging.getLogger(__name__)


class ScrapeReport(BaseModel):
    new_topics: int = 0
    duplicates: int = 0
    errors: list[tuple[str, str]] = []


def _build_sources(config: Config, secrets: Secrets) -> list[Source]:
    sources: list[Source] = []

    if config.sources.rss.enabled:
        sources.append(
            RSSSource(
                feeds=config.sources.rss.feeds,
                max_items_per_feed=config.sources.rss.max_items_per_feed,
            )
        )

    if config.sources.hackernews.enabled:
        sources.append(HackerNewsSource(max_items=config.sources.hackernews.max_items))

    if config.sources.reddit.enabled:
        try:
            sources.append(
                RedditSource(
                    subreddits=config.sources.reddit.subreddits,
                    max_items_per_sub=config.sources.reddit.max_items_per_sub,
                    client_id=secrets.REDDIT_CLIENT_ID,
                    client_secret=secrets.REDDIT_CLIENT_SECRET,
                    user_agent=secrets.REDDIT_USER_AGENT,
                )
            )
        except SourceError as e:
            # Construction failure recorded immediately so it shows in report
            sources.append(_ErrorSource("reddit", str(e)))

    if config.sources.linkedin.enabled:
        sources.append(LinkedInSource())

    if config.sources.twitter.enabled:
        try:
            sources.append(
                TwitterSource(
                    bearer_token=secrets.TWITTER_BEARER_TOKEN,
                    query=config.sources.twitter.query,
                )
            )
        except SourceError as e:
            sources.append(_ErrorSource("twitter", str(e)))

    return sources


class _ErrorSource:
    """Placeholder source that immediately reports a construction-time error."""

    def __init__(self, name: str, msg: str) -> None:
        self.name = name
        self._msg = msg

    def fetch(self):  # type: ignore[override]
        raise SourceError(self._msg)


def run_scraper(
    conn: sqlite3.Connection,
    config: Config,
    secrets: Secrets,
) -> ScrapeReport:
    report = ScrapeReport()
    sources = _build_sources(config, secrets)

    # Track existing ids to detect duplicates within this run
    for source in sources:
        try:
            topics = source.fetch()
        except (SourceError, Exception) as e:
            msg = str(e)
            report.errors.append((source.name, msg))
            logger.warning("%s: ERROR %s", source.name, msg)
            continue

        src_new = 0
        src_dup = 0
        for topic in topics:
            existing_count = conn.execute(
                "SELECT COUNT(*) FROM topics WHERE source=? AND external_id=?",
                (topic.source, topic.external_id),
            ).fetchone()[0]
            upsert_topic(conn, topic)
            if existing_count == 0:
                src_new += 1
            else:
                src_dup += 1

        report.new_topics += src_new
        report.duplicates += src_dup
        logger.info("%s: %d new, %d dup", source.name, src_new, src_dup)

    return report
