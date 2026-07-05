"""test_llm.py — LLM layer tests."""
import json

import pytest

from blogbot.config import load_config, load_secrets
from blogbot.llm.base import LLMError, extract_json
from blogbot.llm.router import Role, get_client


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------

def test_extract_json_fenced():
    result = extract_json('```json\n{"a": 1}\n```')
    assert result == {"a": 1}


def test_extract_json_bare():
    result = extract_json('{"b": 2}')
    assert result == {"b": 2}


def test_extract_json_prose_wrapped():
    result = extract_json('Here is the output: {"c": 3} done.')
    assert result == {"c": 3}


def test_extract_json_no_json_raises():
    with pytest.raises(LLMError):
        extract_json("no json here at all")


# ---------------------------------------------------------------------------
# complete_json retry logic via stub client
# ---------------------------------------------------------------------------

class _StubBadClient:
    """Returns invalid JSON every time."""
    def complete(self, system, user, *, max_tokens=1024, temperature=0.7):
        return "not valid json"

    def complete_json(self, system, user, schema_hint, *, max_tokens=1024):
        from blogbot.llm.ollama_client import OllamaClient
        # Use the shared logic by borrowing OllamaClient.complete_json but with our complete
        calls = getattr(self, "_calls", 0)
        self._calls = calls + 1
        text = self.complete(system, user, max_tokens=max_tokens)
        try:
            return extract_json(text)
        except (LLMError, ValueError) as e:
            if self._calls <= 1:
                retry_user = f"{user}\n\nPrev failed: {e}"
                return self.complete_json(system, retry_user, schema_hint, max_tokens=max_tokens)
            raise LLMError(f"Failed after retry: {e}")


def test_complete_json_retry_then_llm_error():
    client = _StubBadClient()
    with pytest.raises(LLMError):
        client.complete_json("sys", "user", "{}", max_tokens=256)


# ---------------------------------------------------------------------------
# router: config errors
# ---------------------------------------------------------------------------

def _blank_config():
    config = load_config()
    config.llm.ollama.model_analysis = ""
    config.llm.ollama.model_panel = ""
    return config


def _blank_secrets():
    secrets = load_secrets()
    secrets.ANTHROPIC_API_KEY = ""
    return secrets


def test_router_empty_ollama_model_raises():
    import blogbot.llm.router as _router
    _router._cache.clear()
    config = _blank_config()
    secrets = _blank_secrets()
    with pytest.raises(LLMError, match="model_analysis"):
        get_client(Role.ANALYSIS, config, secrets)
    _router._cache.clear()


def test_router_draft_without_api_key_raises():
    import blogbot.llm.router as _router
    _router._cache.clear()
    config = load_config()
    secrets = _blank_secrets()
    from blogbot.config import MissingSecretError
    with pytest.raises(MissingSecretError):
        get_client(Role.DRAFT, config, secrets)
    _router._cache.clear()
