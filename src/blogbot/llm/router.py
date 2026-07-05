from __future__ import annotations

from enum import Enum
from typing import Union

import httpx

from blogbot.config import Config, Secrets, require_secret
from blogbot.llm.anthropic_client import AnthropicClient
from blogbot.llm.base import LLMError
from blogbot.llm.ollama_client import OllamaClient

LLMClient = Union[OllamaClient, AnthropicClient]

_cache: dict[str, LLMClient] = {}


class Role(str, Enum):
    ANALYSIS = "analysis"
    PANEL = "panel"
    DRAFT = "draft"
    IMAGE_PROMPT = "image_prompt"


def get_client(role: Role, config: Config, secrets: Secrets) -> LLMClient:
    if role in _cache:
        return _cache[role]

    client: LLMClient
    if role == Role.DRAFT:
        api_key = require_secret("ANTHROPIC_API_KEY", secrets.ANTHROPIC_API_KEY)
        client = AnthropicClient(api_key=api_key, model=config.llm.anthropic.model_draft)
    elif role in (Role.ANALYSIS, Role.IMAGE_PROMPT):
        model = config.llm.ollama.model_analysis
        if not model:
            raise LLMError("config llm.ollama.model_analysis is empty — set it in config.yaml")
        client = OllamaClient(base_url=config.llm.ollama.base_url, model=model)
    elif role == Role.PANEL:
        model = config.llm.ollama.model_panel
        if not model:
            raise LLMError("config llm.ollama.model_panel is empty — set it in config.yaml")
        client = OllamaClient(base_url=config.llm.ollama.base_url, model=model)
    else:
        raise LLMError(f"Unknown role: {role}")

    _cache[role] = client
    return client


def healthcheck(config: Config, secrets: Secrets) -> dict[str, str]:
    result: dict[str, str] = {}

    # Ollama
    try:
        resp = httpx.get(f"{config.llm.ollama.base_url}/api/tags", timeout=5.0)
        resp.raise_for_status()
        tags_data = resp.json()
        available = {m.get("name", "") for m in tags_data.get("models", [])}
        missing: list[str] = []
        for field, label in [
            (config.llm.ollama.model_analysis, "model_analysis"),
            (config.llm.ollama.model_panel, "model_panel"),
        ]:
            if not field:
                missing.append(f"{label} not set — run: blogbot setup")
            elif field not in available:
                missing.append(f"{label}={field!r} not found in Ollama (available: {sorted(available)[:5]})")
        result["ollama"] = "ok" if not missing else "; ".join(missing)
    except httpx.RequestError as e:
        result["ollama"] = f"connection error: {e} — is Ollama running at {config.llm.ollama.base_url}?"
    except httpx.HTTPStatusError as e:
        result["ollama"] = f"HTTP {e.response.status_code}: {e.response.text[:100]}"

    # Anthropic
    if not secrets.ANTHROPIC_API_KEY:
        result["anthropic"] = "ANTHROPIC_API_KEY missing — run: blogbot setup"
    else:
        try:
            client = AnthropicClient(api_key=secrets.ANTHROPIC_API_KEY, model=config.llm.anthropic.model_draft)
            client.complete(system="ping", user="ping", max_tokens=1)
            result["anthropic"] = "ok"
        except LLMError as e:
            result["anthropic"] = str(e)

    return result
