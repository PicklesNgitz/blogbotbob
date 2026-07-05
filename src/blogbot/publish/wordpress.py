from __future__ import annotations

import logging
from pathlib import Path

import frontmatter as _fm
import httpx
import markdown as _md

from blogbot.agents import PipelineHalt
from blogbot.config import Config, Secrets
from blogbot.db import drafts_by_status, get_draft, update_draft
from blogbot.models import DraftStatus

logger = logging.getLogger(__name__)


class WordPressError(Exception):
    """Raised on WP API errors."""


class WPClient:
    def __init__(self, base_url: str, username: str, app_password: str) -> None:
        self._auth = httpx.BasicAuth(username, app_password)
        self._base = f"{base_url.rstrip('/')}/wp-json/wp/v2"

    def _get(self, path: str, **params) -> httpx.Response:
        return httpx.get(f"{self._base}{path}", auth=self._auth, params=params, timeout=30.0)

    def _post(self, path: str, **kwargs) -> httpx.Response:
        return httpx.post(f"{self._base}{path}", auth=self._auth, timeout=60.0, **kwargs)

    def verify(self) -> str:
        resp = self._get("/users/me")
        if resp.status_code == 401:
            raise WordPressError(
                "WordPress authentication failed (401). "
                "Check WP_USERNAME and WP_APP_PASSWORD in .env — "
                "generate an Application Password in wp-admin → Users → Profile."
            )
        resp.raise_for_status()
        return str(resp.json().get("name", ""))

    def ensure_category(self, name: str) -> int:
        resp = self._get("/categories", search=name, per_page=10)
        resp.raise_for_status()
        for cat in resp.json():
            if cat.get("name", "").lower() == name.lower() or cat.get("slug", "") == name.lower():
                return int(cat["id"])
        create_resp = self._post("/categories", json={"name": name})
        create_resp.raise_for_status()
        return int(create_resp.json()["id"])

    def upload_media(self, png_path: Path, title: str) -> int:
        slug = png_path.stem
        data = png_path.read_bytes()
        resp = httpx.post(
            f"{self._base}/media",
            auth=self._auth,
            content=data,
            headers={
                "Content-Type": "image/png",
                "Content-Disposition": f'attachment; filename="{slug}.png"',
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        return int(resp.json()["id"])

    def _ensure_tag(self, tag: str) -> int:
        resp = self._get("/tags", search=tag, per_page=10)
        resp.raise_for_status()
        for t in resp.json():
            if t.get("name", "").lower() == tag.lower():
                return int(t["id"])
        create_resp = self._post("/tags", json={"name": tag})
        create_resp.raise_for_status()
        return int(create_resp.json()["id"])

    def create_post(
        self,
        *,
        title: str,
        content_html: str,
        excerpt: str,
        category_id: int,
        featured_media: int,
        tags: list[str],
        status: str,
    ) -> tuple[int, str]:
        tag_ids = [self._ensure_tag(t) for t in tags]
        payload = {
            "title": title,
            "content": content_html,
            "excerpt": excerpt,
            "categories": [category_id],
            "featured_media": featured_media,
            "tags": tag_ids,
            "status": status,
        }
        resp = self._post("/posts", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return int(data["id"]), str(data["link"])


def _markdown_to_html(md_text: str) -> str:
    return _md.markdown(md_text, extensions=["extra", "sane_lists"])


def run_publish(
    conn,
    config: Config,
    secrets: Secrets,
    run_id: str | None = None,
) -> list[tuple[int, str]]:
    if not config.wordpress.base_url or not secrets.WP_USERNAME or not secrets.WP_APP_PASSWORD:
        raise PipelineHalt("wordpress not configured — run: blogbot setup")

    client = WPClient(config.wordpress.base_url, secrets.WP_USERNAME, secrets.WP_APP_PASSWORD)
    try:
        display_name = client.verify()
        logger.info("publish: connected as %s", display_name)
    except WordPressError as e:
        raise PipelineHalt(str(e))

    approved = drafts_by_status(conn, DraftStatus.approved, run_id=run_id)
    if not approved:
        return []

    category_id = client.ensure_category(config.wordpress.category)
    results: list[tuple[int, str]] = []

    for draft in approved:
        try:
            post = _fm.loads(draft.markdown)
            body_html = _markdown_to_html(post.content)
            fm_tags: list[str] = list(post.metadata.get("tags", []))
            excerpt = str(post.metadata.get("description", ""))[:155]

            featured_media = 0
            if draft.image_path and Path(draft.image_path).exists():
                featured_media = client.upload_media(Path(draft.image_path), draft.title)
            else:
                logger.warning("publish: no image for draft %d — posting without featured image", draft.id)

            wp_id, wp_url = client.create_post(
                title=draft.title,
                content_html=body_html,
                excerpt=excerpt,
                category_id=category_id,
                featured_media=featured_media,
                tags=fm_tags,
                status=config.wordpress.default_status,
            )
            update_draft(conn, draft.id, wp_post_id=wp_id, wp_url=wp_url, status=DraftStatus.published.value)  # type: ignore[arg-type]
            results.append((wp_id, wp_url))
            logger.info("publish: published draft %d → %s", draft.id, wp_url)

        except Exception as e:
            logger.error("publish: draft %d failed: %s", draft.id, e)
            update_draft(conn, draft.id, status=DraftStatus.failed.value, error_message=str(e))  # type: ignore[arg-type]

    return results
