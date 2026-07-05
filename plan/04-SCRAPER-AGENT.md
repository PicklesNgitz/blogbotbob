# Stage 04 — Scraper Agent & Source Adapters

## Objective
Pluggable source adapters behind one interface; scraper agent runs all ENABLED sources, upserts `Topic` rows. A disabled or failing source must never abort the run — log and continue.

## Files
`src/blogbot/sources/base.py`, `rss.py`, `hackernews.py`, `reddit.py`, `linkedin.py`, `twitter.py`, `src/blogbot/agents/scraper.py`

## 1. `sources/base.py`

```python
class SourceError(Exception): ...

class Source(Protocol):
    name: str
    def fetch(self) -> list[Topic]: ...   # Topic from models.py, status='new', fetched_at=utc_now()
```

## 2. `rss.py` — RSSSource
- Constructor: `RSSSource(feeds: list[str], max_items_per_feed: int)`.
- `feedparser.parse` per feed. Per entry: `external_id` = entry link (fallback entry id), `title`, `url` = link, `summary` = plain-text-stripped `entry.summary` (may be empty), `raw_score` = 0.
- One feed failing → log warning, continue other feeds.

## 3. `hackernews.py` — HackerNewsSource
- No credentials. GET `https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={max_items}` via httpx.
- Per hit: `external_id` = `objectID`, `title`, `url` (fallback `https://news.ycombinator.com/item?id={objectID}`), `summary` = "", `raw_score` = `points`.

## 4. `reddit.py` — RedditSource
- Constructor takes subreddits list, max per sub, plus creds. Use PRAW read-only: `praw.Reddit(client_id=..., client_secret=..., user_agent=...)`.
- `.hot(limit=max)` per subreddit, skip stickied. `external_id` = submission id, `raw_score` = score, `summary` = selftext first 500 chars.
- Missing creds at construction → raise `SourceError("reddit enabled but REDDIT_CLIENT_ID/SECRET missing in .env")`.

## 5. `linkedin.py` — LinkedInSource (experimental, default disabled)
- v1: STUB. `fetch()` raises `SourceError("linkedin source not implemented in v1 — disable in config.yaml")`.
- Do NOT implement browser automation in v1. (Recorded future work in README.)

## 6. `twitter.py` — TwitterSource
- GET `https://api.twitter.com/2/tweets/search/recent?query={query}&max_results=25` with bearer token header.
- Query built from config addition — add to `config.yaml` under `sources.twitter`: `query: ""` (user supplies).
- `external_id` = tweet id, `title` = first 100 chars of text, `summary` = full text, `raw_score` = 0 (metrics need extra params; skip v1).
- Missing bearer → `SourceError` naming `TWITTER_BEARER_TOKEN`.

## 7. `agents/scraper.py`

```python
def run_scraper(conn, config: Config, secrets: Secrets) -> ScrapeReport
```
- Build list of enabled sources from config. For each: `fetch()` inside try/except `SourceError`/`Exception` — on error, record `(source_name, error_str)` in report, continue.
- Upsert every topic; count new vs duplicate.
- `ScrapeReport` (Pydantic): `new_topics: int`, `duplicates: int`, `errors: list[tuple[str, str]]`.
- Log one summary line per source: `rss: 14 new, 6 dup` / `reddit: ERROR <msg>`.

## 8. CLI
Add `blogbot scrape` command: runs scraper standalone, prints report. Errors list printed but exit code stays 0 if at least one source succeeded; exit 1 only if ALL enabled sources errored.

## 9. Build-time verification (no user input, no real creds)
Hacker News needs no credentials — it is the build-time smoke test. Temporarily rely on `hackernews.enabled: true` default; RSS with empty `feeds` list returns zero topics without error.

## Acceptance criteria
- [ ] `blogbot scrape` (default config, HN only) exits 0, ≥5 topics in DB
- [ ] Re-running `blogbot scrape` immediately: duplicates counted, no unique-constraint crash
- [ ] Setting `hackernews.enabled: false` too (all sources dead) + run → exits 1 with clear message; revert after
- [ ] Reddit enabled without creds → run continues, report lists reddit error naming the `.env` keys
- [ ] Commit: `feat: scraper agent with rss/hn/reddit/twitter adapters`
