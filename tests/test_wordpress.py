"""Stage 10 AC1: WPClient unit tests with pytest-httpx."""
import json

import pytest
from httpx import Response
from pytest_httpx import HTTPXMock

from blogbot.publish.wordpress import WPClient, WordPressError

BASE = "http://wp.test"


@pytest.fixture
def client():
    return WPClient(BASE, "admin", "secret")


# ---------------------------------------------------------------------------
# verify()
# ---------------------------------------------------------------------------

def test_verify_ok(httpx_mock: HTTPXMock, client: WPClient):
    httpx_mock.add_response(json={"name": "Admin"})
    assert client.verify() == "Admin"


def test_verify_401(httpx_mock: HTTPXMock, client: WPClient):
    httpx_mock.add_response(status_code=401, json={})
    with pytest.raises(WordPressError, match="401"):
        client.verify()


# ---------------------------------------------------------------------------
# ensure_category()
# ---------------------------------------------------------------------------

def test_ensure_category_found(httpx_mock: HTTPXMock, client: WPClient):
    httpx_mock.add_response(json=[{"id": 7, "name": "AI", "slug": "ai"}])
    assert client.ensure_category("AI") == 7


def test_ensure_category_created(httpx_mock: HTTPXMock, client: WPClient):
    httpx_mock.add_response(json=[])  # GET /categories search → empty
    httpx_mock.add_response(json={"id": 42})  # POST /categories
    assert client.ensure_category("NewCat") == 42


# ---------------------------------------------------------------------------
# upload_media() — Content-Disposition filename check
# ---------------------------------------------------------------------------

def test_upload_media_content_disposition(httpx_mock: HTTPXMock, client: WPClient, tmp_path):
    png = tmp_path / "my-post.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    captured = {}

    def check_upload(request):
        captured["disposition"] = request.headers.get("Content-Disposition", "")
        return Response(200, json={"id": 99})

    httpx_mock.add_callback(check_upload)
    result = client.upload_media(png, "My Post")
    assert result == 99
    assert 'filename="my-post.png"' in captured["disposition"]


# ---------------------------------------------------------------------------
# create_post() — payload correctness
# ---------------------------------------------------------------------------

def test_create_post_payload(httpx_mock: HTTPXMock, client: WPClient):
    # _ensure_tag: GET search → empty, POST → id 11
    httpx_mock.add_response(json=[])      # GET /tags?search=ai
    httpx_mock.add_response(json={"id": 11})   # POST /tags

    captured = {}

    def check_post(request):
        captured["body"] = json.loads(request.content)
        return Response(200, json={"id": 1, "link": "https://wp.test/test-post/"})

    httpx_mock.add_callback(check_post)

    post_id, link = client.create_post(
        title="Test Post",
        content_html="<p>body</p>",
        excerpt="short",
        category_id=7,
        featured_media=99,
        tags=["ai"],
        status="draft",
    )
    assert post_id == 1
    assert "test-post" in link
    body = captured["body"]
    assert body["title"] == "Test Post"
    assert body["status"] == "draft"
    assert body["categories"] == [7]
    assert body["featured_media"] == 99
    assert 11 in body["tags"]
