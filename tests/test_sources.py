"""test_sources.py — source adapter tests."""
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from blogbot.sources.hackernews import HackerNewsSource
from blogbot.sources.reddit import RedditSource
from blogbot.sources.rss import RSSSource
from blogbot.sources.base import SourceError
from blogbot.agents.scraper import run_scraper, ScrapeReport
from blogbot.config import load_config, load_secrets

FIXTURE_FEED = str(Path(__file__).parent / "fixtures" / "feed.xml")


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------

def test_rss_parse_fixture():
    source = RSSSource(feeds=[FIXTURE_FEED], max_items_per_feed=10)
    topics = source.fetch()
    assert len(topics) == 2
    titles = [t.title for t in topics]
    assert "AI Transforms SMB Operations" in titles
    assert all(t.source == "rss" for t in topics)
    assert all(t.url for t in topics)
    # HTML stripped from description
    for t in topics:
        assert "<p>" not in (t.summary or "")


# ---------------------------------------------------------------------------
# HackerNews (mocked)
# ---------------------------------------------------------------------------

def test_hackernews_topics(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        json={
            "hits": [
                {"objectID": "42", "title": "HN Story", "url": "https://example.com/story", "points": 99},
                {"objectID": "43", "title": "HN Story 2", "url": None, "points": 50},
            ]
        }
    )
    source = HackerNewsSource(max_items=5)
    topics = source.fetch()
    assert len(topics) == 2
    assert topics[0].raw_score == 99.0
    assert topics[0].external_id == "42"
    # Fallback URL when url is None
    assert "news.ycombinator.com" in topics[1].url


# ---------------------------------------------------------------------------
# Reddit — missing creds
# ---------------------------------------------------------------------------

def test_reddit_missing_creds_source_error():
    with pytest.raises(SourceError, match="REDDIT_CLIENT_ID"):
        RedditSource(subreddits=["python"], max_items_per_sub=5,
                     client_id="", client_secret="", user_agent="test")


# ---------------------------------------------------------------------------
# Scraper continues when one source raises
# ---------------------------------------------------------------------------

def test_scraper_continues_on_source_error(conn):
    from blogbot.sources.base import SourceError, Source
    from blogbot.models import Topic
    from blogbot.db import utc_now

    class GoodSource:
        name = "good"
        def fetch(self):
            return [Topic(source="good", external_id="g1", title="Good", fetched_at=utc_now())]

    class BadSource:
        name = "bad"
        def fetch(self):
            raise SourceError("bad source failed")

    import blogbot.agents.scraper as _mod
    orig_build = _mod._build_sources

    def stub_build(config, secrets):
        return [GoodSource(), BadSource()]

    _mod._build_sources = stub_build

    config = load_config()
    secrets = load_secrets()
    report = run_scraper(conn, config, secrets)

    _mod._build_sources = orig_build

    assert report.new_topics == 1
    assert len(report.errors) == 1
    assert report.errors[0][0] == "bad"
