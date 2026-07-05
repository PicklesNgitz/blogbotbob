from __future__ import annotations

import httpx

from blogbot.db import utc_now
from blogbot.models import Topic
from blogbot.sources.base import SourceError

_HN_URL = "https://hn.algolia.com/api/v1/search"


class HackerNewsSource:
    name = "hackernews"

    def __init__(self, max_items: int) -> None:
        self.max_items = max_items

    def fetch(self) -> list[Topic]:
        try:
            resp = httpx.get(
                _HN_URL,
                params={"tags": "front_page", "hitsPerPage": self.max_items},
                timeout=30.0,
            )
            resp.raise_for_status()
        except httpx.RequestError as e:
            raise SourceError(f"hackernews connection error: {e}") from e
        except httpx.HTTPStatusError as e:
            raise SourceError(f"hackernews HTTP {e.response.status_code}") from e

        hits = resp.json().get("hits", [])
        topics: list[Topic] = []
        now = utc_now()
        for hit in hits:
            obj_id = str(hit.get("objectID", ""))
            title = (hit.get("title") or "").strip()
            if not obj_id or not title:
                continue
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={obj_id}"
            topics.append(
                Topic(
                    source="hackernews",
                    external_id=obj_id,
                    title=title,
                    url=url,
                    summary="",
                    raw_score=float(hit.get("points") or 0),
                    fetched_at=now,
                )
            )
        return topics
