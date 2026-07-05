from __future__ import annotations

import json

import anthropic as _anthropic

from blogbot.llm.base import LLMError, extract_json


class AnthropicClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = _anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        try:
            msg = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=temperature,
            )
        except _anthropic.APIError as e:
            raise LLMError(f"Anthropic API error: {e}") from e
        return "".join(block.text for block in msg.content if hasattr(block, "text"))

    def complete_json(
        self,
        system: str,
        user: str,
        schema_hint: str,
        *,
        max_tokens: int = 1024,
    ) -> dict:
        json_system = f"{system}\n\nRespond with ONLY a JSON object matching this schema:\n{schema_hint}"
        text = self.complete(json_system, user, max_tokens=max_tokens, temperature=0.0)
        try:
            return extract_json(text)
        except (LLMError, ValueError, json.JSONDecodeError) as first_err:
            retry_user = f"{user}\n\nYour previous response failed to parse as JSON: {first_err}\nReturn ONLY a valid JSON object."
            text2 = self.complete(json_system, retry_user, max_tokens=max_tokens, temperature=0.0)
            try:
                return extract_json(text2)
            except (LLMError, ValueError, json.JSONDecodeError) as e:
                raise LLMError(f"Anthropic JSON parse failed after retry: {e}\nResponse: {text2[:300]}") from e
