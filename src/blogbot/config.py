from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, model_validator


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class MissingSecretError(Exception):
    """Raised when a required secret is absent from .env."""


# ---------------------------------------------------------------------------
# Config models (mirror config.yaml exactly)
# ---------------------------------------------------------------------------

class RssSourceConfig(BaseModel):
    enabled: bool = True
    feeds: list[str] = []
    max_items_per_feed: int = 20

    model_config = {"extra": "forbid"}


class HackerNewsSourceConfig(BaseModel):
    enabled: bool = True
    max_items: int = 30

    model_config = {"extra": "forbid"}


class RedditSourceConfig(BaseModel):
    enabled: bool = False
    subreddits: list[str] = []
    max_items_per_sub: int = 20

    model_config = {"extra": "forbid"}


class LinkedInSourceConfig(BaseModel):
    enabled: bool = False

    model_config = {"extra": "forbid"}


class TwitterSourceConfig(BaseModel):
    enabled: bool = False

    model_config = {"extra": "forbid"}


class SourcesConfig(BaseModel):
    rss: RssSourceConfig = RssSourceConfig()
    hackernews: HackerNewsSourceConfig = HackerNewsSourceConfig()
    reddit: RedditSourceConfig = RedditSourceConfig()
    linkedin: LinkedInSourceConfig = LinkedInSourceConfig()
    twitter: TwitterSourceConfig = TwitterSourceConfig()

    model_config = {"extra": "forbid"}


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model_analysis: str = ""
    model_panel: str = ""

    model_config = {"extra": "forbid"}


class AnthropicLLMConfig(BaseModel):
    model_draft: str = "claude-sonnet-4-6"
    max_tokens_draft: int = 4096

    model_config = {"extra": "forbid"}


class LLMConfig(BaseModel):
    ollama: OllamaConfig = OllamaConfig()
    anthropic: AnthropicLLMConfig = AnthropicLLMConfig()

    model_config = {"extra": "forbid"}


class PanelConfig(BaseModel):
    personas_file: str = "personas.yaml"
    scores_per_draft: int = 5

    model_config = {"extra": "forbid"}


class ComfyUIConfig(BaseModel):
    base_url: str = "http://localhost:8188"
    workflow_file: str = "comfy_workflow.json"
    width: int = 1200
    height: int = 630
    timeout_seconds: int = 300

    model_config = {"extra": "forbid"}


class ImageryConfig(BaseModel):
    comfyui: ComfyUIConfig = ComfyUIConfig()

    model_config = {"extra": "forbid"}


class WordPressConfig(BaseModel):
    base_url: str = ""
    default_status: str = "draft"
    category: str = "AI"

    model_config = {"extra": "forbid"}


class DraftingConfig(BaseModel):
    posts_per_run: int = 6
    min_words: int = 700
    max_words: int = 1200

    model_config = {"extra": "forbid"}


class RunConfig(BaseModel):
    max_publishes_per_run: int = 2
    panel_top_fraction: float = 0.30

    model_config = {"extra": "forbid"}


class Config(BaseModel):
    run: RunConfig = RunConfig()
    sources: SourcesConfig = SourcesConfig()
    llm: LLMConfig = LLMConfig()
    panel: PanelConfig = PanelConfig()
    imagery: ImageryConfig = ImageryConfig()
    wordpress: WordPressConfig = WordPressConfig()
    drafting: DraftingConfig = DraftingConfig()

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Secrets model
# ---------------------------------------------------------------------------

class Secrets(BaseModel):
    ANTHROPIC_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "blogbotbob/0.1"
    TWITTER_BEARER_TOKEN: str = ""
    LINKEDIN_EMAIL: str = ""
    LINKEDIN_PASSWORD: str = ""
    WP_USERNAME: str = ""
    WP_APP_PASSWORD: str = ""

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(path: Path = Path("config.yaml")) -> Config:
    """Parse config.yaml into a Config model. Unknown keys raise an error."""
    if not path.exists():
        return Config()
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return Config.model_validate(raw)


def save_config(config: Config, path: Path = Path("config.yaml")) -> None:
    """Dump Config back to YAML preserving the canonical key order."""
    _KEY_ORDER = [
        "run", "sources", "llm", "panel", "imagery", "wordpress", "drafting"
    ]
    data = config.model_dump()
    ordered: dict = {k: data[k] for k in _KEY_ORDER if k in data}
    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(ordered, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)


def load_secrets(env_path: Path = Path(".env")) -> Secrets:
    """Load .env via dotenv, return Secrets model (all fields optional)."""
    load_dotenv(dotenv_path=env_path, override=False)
    return Secrets(
        ANTHROPIC_API_KEY=os.getenv("ANTHROPIC_API_KEY", ""),
        REDDIT_CLIENT_ID=os.getenv("REDDIT_CLIENT_ID", ""),
        REDDIT_CLIENT_SECRET=os.getenv("REDDIT_CLIENT_SECRET", ""),
        REDDIT_USER_AGENT=os.getenv("REDDIT_USER_AGENT", "blogbotbob/0.1"),
        TWITTER_BEARER_TOKEN=os.getenv("TWITTER_BEARER_TOKEN", ""),
        LINKEDIN_EMAIL=os.getenv("LINKEDIN_EMAIL", ""),
        LINKEDIN_PASSWORD=os.getenv("LINKEDIN_PASSWORD", ""),
        WP_USERNAME=os.getenv("WP_USERNAME", ""),
        WP_APP_PASSWORD=os.getenv("WP_APP_PASSWORD", ""),
    )


def require_secret(name: str, value: str) -> str:
    """Return value if non-empty; raise MissingSecretError naming the .env key."""
    if not value:
        raise MissingSecretError(
            f"Required secret '{name}' is missing. Set it in your .env file."
        )
    return value


def write_env(updates: dict[str, str], path: Path = Path(".env")) -> None:
    """Create .env from .env.example if absent; set/replace only the given keys."""
    example = path.parent / ".env.example"
    if not path.exists() and example.exists():
        path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    elif not path.exists():
        path.write_text("", encoding="utf-8")

    lines = path.read_text(encoding="utf-8").splitlines()
    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
