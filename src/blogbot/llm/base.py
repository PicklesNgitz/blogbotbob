from __future__ import annotations

import json
import re
from typing import Protocol, runtime_checkable


class LLMError(Exception):
    """Raised on provider errors, connection failures, or JSON parse failures."""


def extract_json(text: str) -> dict:
    """Strip markdown fences, find first { … last }, parse as JSON."""
    stripped = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"No JSON object found in response: {text[:200]!r}")
    return json.loads(stripped[start : end + 1])


@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str: ...

    def complete_json(
        self,
        system: str,
        user: str,
        schema_hint: str,
        *,
        max_tokens: int = 1024,
    ) -> dict: ...
