# Stage 08 — Image Agent (ComfyUI SDXL)

## Objective
Header image per `selected` draft: Ollama writes an SDXL prompt from the draft, ComfyUI API renders it, PNG saved to `data/images/{slug}.png`, draft → `image_ready`.

## Files
`src/blogbot/agents/imagery.py`, `comfy_workflow.json` (repo root)

## 1. Runtime configuration (no user input at build time)
ComfyUI URL and SDXL checkpoint name are collected by the `blogbot setup` wizard (Stage 11 §0), which queries `GET {base}/object_info` live and lets the user pick from their installed `CheckpointLoaderSimple` options. Add config key now: `imagery.comfyui.checkpoint: ""` (empty default). `run_imagery` with empty checkpoint → `PipelineHalt("comfyui checkpoint not set — run: blogbot setup")`. Users with an existing workflow JSON can replace `comfy_workflow.json` manually; README documents the substitution placeholders.

## 2. `comfy_workflow.json` (minimal API format, checkpoint substituted at runtime)
Nodes: `CheckpointLoaderSimple` → `CLIPTextEncode` (positive) + `CLIPTextEncode` (negative) → `EmptyLatentImage` (width/height from config) → `KSampler` (steps 25, cfg 7.0, sampler `euler`, scheduler `normal`, denoise 1.0) → `VAEDecode` → `SaveImage` (filename_prefix `blogbot`).
Placeholders the code substitutes at runtime: positive text, seed, width, height. Negative text fixed: `text, watermark, logo, low quality, blurry, deformed`.

## 3. Prompt generation (role IMAGE_PROMPT, Ollama)
System: `You write concise Stable Diffusion XL prompts for professional blog header images. No text or words in the image. Answer ONLY JSON.`
User: `Blog title: {title}\nDescription: {description}\nWrite one SDXL prompt: editorial, modern, abstract-professional, suitable as a wide header. JSON schema: {"prompt": str}`
Store result in `drafts.image_prompt`.

## 4. ComfyUI client (inside `imagery.py`, no separate module)

```python
def render(base_url: str, workflow: dict, timeout: float) -> bytes  # PNG bytes
```
1. POST `{base}/prompt` with `{"prompt": workflow}` → `prompt_id`.
2. Poll `GET {base}/history/{prompt_id}` every 2 s until outputs present or timeout (config `imagery.comfyui.timeout_seconds`) → timeout raises `ImageError`.
3. From history outputs take first image `{filename, subfolder, type}` → GET `{base}/view?filename=...&subfolder=...&type=...` → bytes.

Seed: `random.randint(0, 2**32-1)` per render.

## 5. Entry point

```python
def run_imagery(conn, config: Config, secrets: Secrets, run_id: str) -> None
```
Per `selected` draft: prompt → render → write `data/images/{slug}.png` → `update_draft(image_path=..., image_prompt=..., status="image_ready")`.
Failure per draft: retry render once; then mark draft `failed` + `error_message` and continue others. IMPORTANT: a failed image must NOT block other drafts.

## 6. CLI
`blogbot imagery --run-id <id>`. After run, print saved file paths. Visual quality review happens in Stage 14 with the user.

## Acceptance criteria (build-time: mocked ComfyUI)
- [ ] Unit test: `render` against mocked httpx (prompt→history→view sequence) returns bytes; timeout path raises `ImageError`
- [ ] Unit test: workflow JSON substitution fills prompt/seed/size/checkpoint placeholders
- [ ] `blogbot imagery` with empty checkpoint config exits 1 with `run: blogbot setup` guidance
- [ ] Real render deferred to Stage 14
- [ ] Commit: `feat: image agent renders headers via ComfyUI`
