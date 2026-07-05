# Stage 10 — WordPress Publisher

## Objective
Publish `approved` drafts to WordPress via REST API with Application Password auth: upload header image as media, create post with featured image, record `wp_post_id`/`wp_url`, status → `published`.

## File
`src/blogbot/publish/wordpress.py`

## 1. Runtime configuration (no user input at build time)
WordPress base URL, username, Application Password, and category are collected by the `blogbot setup` wizard (Stage 11 §0). Empty `wordpress.base_url` or missing `WP_USERNAME`/`WP_APP_PASSWORD` at publish time → `PipelineHalt("wordpress not configured — run: blogbot setup")`. The wizard's WP step runs `verify()` live and re-prompts on 401.

## 2. Client

```python
class WordPressError(Exception): ...

class WPClient:
    def __init__(self, base_url: str, username: str, app_password: str): ...
    # httpx.BasicAuth(username, app_password); base = f"{base_url}/wp-json/wp/v2"
    def verify(self) -> str                    # GET /users/me → returns display name; 401 → WordPressError with fix hint
    def ensure_category(self, name: str) -> int  # GET /categories?search=; exact-match slug/name; miss → POST /categories
    def upload_media(self, png_path: Path, title: str) -> int
        # POST /media, headers Content-Type: image/png,
        # Content-Disposition: attachment; filename="{slug}.png" → media id
    def create_post(self, *, title: str, content_html: str, excerpt: str,
                    category_id: int, featured_media: int, tags: list[str],
                    status: str) -> tuple[int, str]   # (post id, link)
        # tags: GET /tags?search= per tag, create missing via POST /tags
```

Markdown → HTML: add dependency `markdown>=3.6` to `pyproject.toml`; convert body (frontmatter stripped) with extensions `["extra", "sane_lists"]`.

## 3. Entry point

```python
def run_publish(conn, config: Config, secrets: Secrets, run_id: str | None = None) -> list[tuple[int, str]]
```
- `verify()` first; failure → `PipelineHalt` with exact error.
- Per `approved` draft: upload media (skip upload if `image_path` empty/missing — post without featured image, log warning) → create post with `status=config.wordpress.default_status` → `update_draft(wp_post_id=..., wp_url=..., status="published")`.
- Per-draft API failure: mark that draft `failed` + `error_message`, continue others.

## 4. First-run safety
`wordpress.default_status` ships as `draft` (set in Stage 01). First real publish lands as a WP DRAFT for the user to eyeball in wp-admin. Stage 14 step 6 flips to `publish` only on the user's explicit yes.

## 5. CLI
`blogbot publish` — prints per-draft `published: {wp_url}` or failure reason.

## Acceptance criteria (build-time: mocked WP API)
- [ ] Unit tests (pytest-httpx): verify() 200/401 paths; ensure_category found/created; create_post payload correct; upload_media sets Content-Disposition filename
- [ ] `blogbot publish` unconfigured exits 1 with `run: blogbot setup` guidance
- [ ] `blogbot publish` with zero approved drafts prints `Nothing approved to publish.` exit 0
- [ ] Real publish deferred to Stage 14
- [ ] Commit: `feat: wordpress publisher with media upload`
