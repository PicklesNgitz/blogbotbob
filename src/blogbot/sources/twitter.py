from __future__ import annotations

import httpx

from blogbot.db import utc_now
from blogbot.models import Topic
from blogbot.sources.base import SourceError

_TWITTER_URL = "https://api.twitter.com/2/tweets/search/recent"


class TwitterSource:
    name = "twitter"

    def __init__(self, bearer_token: str, query: str) -> None:
        if not bearer_token:
            raise SourceError(
                "twitter enabled but TWITTER_BEARER_TOKEN missing in .env"
            )
        self.bearer_token = bearer_token
        self.query = query

    def fetch(self) -> list[Topic]:
        if not self.query:
            raise SourceError("sources.twitter.query is empty — set it in config.yaml")
        try:
            resp = httpx.get(
                _TWITTER_URL,
                params={"query": self.query, "max_results": 25},
                headers={"Authorization": f"Bearer {self.bearer_token}"},
                timeout=30.0,
            )
            resp.raise_for_status()
        except httpx.RequestError as e:
            raise SourceError(f"twitter connection error: {e}") from e
        except httpx.HTTPStatusError as e:
            raise SourceError(f"twitter HTTP {e.response.status_code}: {e.response.text[:100]}") from e

        data = resp.json().get("data", [])
        now = utc_now()
        topics: list[Topic] = []
        for tweet in data:
            tweet_id = str(tweet.get("id", ""))
            text = tweet.get("text", "")
            if not tweet_id or not text:
                continue
            topics.append(
                Topic(
                    source="twitter",
                    external_id=tweet_id,
                    title=text[:100],
                    url=None,
                    summary=text,
                    raw_score=0.0,
                    fetched_at=now,
                )
            )
        return topics
