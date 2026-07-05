from __future__ import annotations

import logging
import re

import feedparser

from blogbot.db import utc_now
from blogbot.models import Topic

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


class RSSSource:
    name = "rss"

    def __init__(self, feeds: list[str], max_items_per_feed: int) -> None:
        self.feeds = feeds
        self.max_items_per_feed = max_items_per_feed

    def fetch(self) -> list[Topic]:
        topics: list[Topic] = []
        for feed_url in self.feeds:
            try:
                parsed = feedparser.parse(feed_url)
                entries = parsed.entries[: self.max_items_per_feed]
                for entry in entries:
                    external_id = getattr(entry, "link", None) or getattr(entry, "id", None)
                    if not external_id:
                        continue
                    title = getattr(entry, "title", "").strip()
                    if not title:
                        continue
                    summary_raw = getattr(entry, "summary", "") or ""
                    topics.append(
                        Topic(
                            source="rss",
                            external_id=external_id,
                            title=title,
                            url=getattr(entry, "link", None),
                            summary=_strip_html(summary_raw)[:500],
                            raw_score=0.0,
                            fetched_at=utc_now(),
                        )
                    )
            except Exception as e:
                logger.warning("rss feed %s failed: %s", feed_url, e)
        return topics
