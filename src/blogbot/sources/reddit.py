from __future__ import annotations

import praw

from blogbot.db import utc_now
from blogbot.models import Topic
from blogbot.sources.base import SourceError


class RedditSource:
    name = "reddit"

    def __init__(
        self,
        subreddits: list[str],
        max_items_per_sub: int,
        client_id: str,
        client_secret: str,
        user_agent: str,
    ) -> None:
        if not client_id or not client_secret:
            raise SourceError(
                "reddit enabled but REDDIT_CLIENT_ID/SECRET missing in .env"
            )
        self._reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        self.subreddits = subreddits
        self.max_items_per_sub = max_items_per_sub

    def fetch(self) -> list[Topic]:
        topics: list[Topic] = []
        now = utc_now()
        for sub_name in self.subreddits:
            sub = self._reddit.subreddit(sub_name)
            for submission in sub.hot(limit=self.max_items_per_sub):
                if submission.stickied:
                    continue
                topics.append(
                    Topic(
                        source="reddit",
                        external_id=submission.id,
                        title=submission.title,
                        url=submission.url,
                        summary=(submission.selftext or "")[:500],
                        raw_score=float(submission.score),
                        fetched_at=now,
                    )
                )
        return topics
