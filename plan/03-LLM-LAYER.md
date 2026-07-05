# Stage 03 — LLM Layer (Hybrid Ollama + Anthropic)

## Objective
One narrow interface both providers implement; a router that maps pipeline roles to providers per locked decisions. Agents never import provider clients directly — only the router.

## Files
`src/blogbot/llm/base.py`, `ollama_client.py`, `anthropic_client.py`, `router.py`

## 1. `base.py`

```python
class LLMError(Exception): ...

class LLMClient(Protocol):
    def complete(self, system: str, user: str, *, max_tokens: int = 1024, temperature: float = 0.7) -> str: ...
    def complete_json(self, system: str, user: str, schema_hint: str, *, max_tokens: int = 1024) -> dict: ...
```

`complete_json` contract: instruct model to emit ONLY a JSON object matching `schema_hint` (a human-readable schema description embedded in the prompt). Parse with `json.loads`; on parse failure retry ONCE with the parse error appended to the prompt; second failure raises `LLMError`.
Shared helper `extract_json(text: str) -> dict` in `base.py`: strip markdown fences, find first `{`...last `}`, parse.

## 2. `ollama_client.py`
- Constructor: `OllamaClient(base_url: str, model: str, timeout: float = 120.0)`.
- `complete`: POST `{base_url}/api/chat`, body `{"model": model, "messages": [{"role":"system",...},{"role":"user",...}], "stream": false, "options": {"temperature": temperature, "num_predict": max_tokens}}` via `httpx`. Return `resp.json()["message"]["content"]`.
- Connection error / non-200 / timeout → raise `LLMError` with the exact underlying message.
- `complete_json` via shared contract in §1.

## 3. `anthropic_client.py`
- Constructor: `AnthropicClient(api_key: str, model: str)`. Uses `anthropic` SDK, `client.messages.create`.
- `complete`: system param + one user message; return concatenated text blocks.
- API errors → wrap in `LLMError` (keep original message).
- `complete_json` via shared contract.

## 4. `router.py`

```python
class Role(str, Enum):
    ANALYSIS = "analysis"   # → Ollama, config llm.ollama.model_analysis
    PANEL = "panel"         # → Ollama, config llm.ollama.model_panel
    DRAFT = "draft"         # → Anthropic, config llm.anthropic.model_draft
    IMAGE_PROMPT = "image_prompt"  # → Ollama, model_analysis

def get_client(role: Role, config: Config, secrets: Secrets) -> LLMClient
```
- Anthropic roles call `require_secret("ANTHROPIC_API_KEY", ...)`.
- Ollama roles: if the configured model name is empty string → raise `LLMError("config llm.ollama.model_X is empty — set it in config.yaml")`.
- Cache clients per (role) within process (simple module-level dict).

## 5. Connectivity check
`router.healthcheck(config, secrets) -> dict[str, str]` — returns `{"ollama": "ok"|error-msg, "anthropic": "ok"|error-msg}`:
- Ollama: GET `{base_url}/api/tags`; also verify both configured model names appear in the tag list, else error string naming the missing model.
- Anthropic: 1-token `complete` call on the draft model ("ping" → any reply is ok).

Wire a CLI command now: `blogbot healthcheck` in `cli.py` printing both lines.

## 6. Unconfigured behavior (build-time requirement)
No credentials exist at build time. `healthcheck` against an unconfigured install must NOT crash: each line reports a clear actionable error, e.g. `anthropic: ANTHROPIC_API_KEY missing — run: blogbot setup`, `ollama: model_analysis not set — run: blogbot setup`. Real `ok/ok` verification happens in Stage 14 after the user runs the wizard.

## Acceptance criteria
- [ ] `blogbot healthcheck` on the unconfigured install exits cleanly with two actionable error lines (no traceback)
- [ ] Both clients pass unit tests with mocked transports (Stage 12 covers; smoke-verify imports now)
- [ ] `extract_json` unit-testable: fenced JSON, bare JSON, and prose-wrapped JSON all parse
- [ ] Commit: `feat: hybrid LLM layer with role router and healthcheck`
