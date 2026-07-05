from __future__ import annotations

import json

import httpx

from blogbot.llm.base import LLMError, extract_json


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.TimeoutException as e:
            raise LLMError(f"Ollama timeout: {e}") from e
        except httpx.HTTPStatusError as e:
            raise LLMError(f"Ollama HTTP {e.response.status_code}: {e.response.text[:200]}") from e
        except httpx.RequestError as e:
            raise LLMError(f"Ollama connection error: {e}") from e
        return resp.json()["message"]["content"]

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
                raise LLMError(f"Ollama JSON parse failed after retry: {e}\nResponse: {text2[:300]}") from e
