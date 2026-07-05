from __future__ import annotations

import copy
import json
import logging
import random
import time
from pathlib import Path

import httpx

from blogbot.agents import PipelineHalt
from blogbot.config import Config, Secrets
from blogbot.db import drafts_by_status, update_draft
from blogbot.llm.router import Role, get_client
from blogbot.models import DraftStatus

logger = logging.getLogger(__name__)

_PROMPT_SYSTEM = (
    "You write concise Stable Diffusion XL prompts for professional blog header images. "
    "No text or words in the image. Answer ONLY JSON."
)
_PROMPT_SCHEMA = '{"prompt": str}'


class ImageError(Exception):
    """Raised on ComfyUI render failure or timeout."""


def _substitute_workflow(
    workflow: dict,
    positive_prompt: str,
    seed: int,
    width: int,
    height: int,
    checkpoint: str,
) -> dict:
    wf = copy.deepcopy(workflow)

    def _sub(val):
        if isinstance(val, str):
            val = val.replace("{{POSITIVE_PROMPT}}", positive_prompt)
            val = val.replace("{{CHECKPOINT}}", checkpoint)
            if val == "{{SEED}}":
                return seed
            if val == "{{WIDTH}}":
                return width
            if val == "{{HEIGHT}}":
                return height
            return val
        return val

    for node in wf.values():
        inputs = node.get("inputs", {})
        for k, v in inputs.items():
            inputs[k] = _sub(v)
    return wf


def render(base_url: str, workflow: dict, timeout: float) -> bytes:
    base = base_url.rstrip("/")
    resp = httpx.post(f"{base}/prompt", json={"prompt": workflow}, timeout=10.0)
    resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hist_resp = httpx.get(f"{base}/history/{prompt_id}", timeout=10.0)
        hist_resp.raise_for_status()
        history = hist_resp.json()
        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            for node_outputs in outputs.values():
                images = node_outputs.get("images", [])
                if images:
                    img = images[0]
                    view_resp = httpx.get(
                        f"{base}/view",
                        params={
                            "filename": img["filename"],
                            "subfolder": img.get("subfolder", ""),
                            "type": img.get("type", "output"),
                        },
                        timeout=30.0,
                    )
                    view_resp.raise_for_status()
                    return view_resp.content
        time.sleep(2.0)

    raise ImageError(f"ComfyUI render timed out after {timeout}s for prompt_id={prompt_id}")


def _load_workflow(workflow_file: str) -> dict:
    path = Path(workflow_file)
    if not path.exists():
        path = Path("comfy_workflow.json")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def run_imagery(
    conn,
    config: Config,
    secrets: Secrets,
    run_id: str,
) -> None:
    if not config.imagery.comfyui.checkpoint:
        raise PipelineHalt("comfyui checkpoint not set — run: blogbot setup")

    drafts = drafts_by_status(conn, DraftStatus.selected, run_id=run_id)
    if not drafts:
        raise PipelineHalt("no selected drafts for this run; run panel first")

    llm_client = get_client(Role.IMAGE_PROMPT, config, secrets)
    workflow_template = _load_workflow(config.imagery.comfyui.workflow_file)
    comfy_cfg = config.imagery.comfyui
    images_dir = Path("data/images")
    images_dir.mkdir(parents=True, exist_ok=True)

    for draft in drafts:
        # Generate SDXL prompt from draft
        import frontmatter as _fm
        try:
            post = _fm.loads(draft.markdown)
            description = str(post.metadata.get("description", ""))
        except Exception:
            description = ""

        user_prompt = (
            f"Blog title: {draft.title}\n"
            f"Description: {description}\n"
            "Write one SDXL prompt: editorial, modern, abstract-professional, "
            f"suitable as a wide header. JSON schema: {_PROMPT_SCHEMA}"
        )
        try:
            result = llm_client.complete_json(_PROMPT_SYSTEM, user_prompt, _PROMPT_SCHEMA, max_tokens=256)
            sdxl_prompt = str(result.get("prompt", draft.title))
        except Exception as e:
            sdxl_prompt = draft.title
            logger.warning("imagery: prompt gen failed for %r: %s", draft.title, e)

        update_draft(conn, draft.id, image_prompt=sdxl_prompt)  # type: ignore[arg-type]

        seed = random.randint(0, 2**32 - 1)
        workflow = _substitute_workflow(
            workflow_template,
            positive_prompt=sdxl_prompt,
            seed=seed,
            width=comfy_cfg.width,
            height=comfy_cfg.height,
            checkpoint=comfy_cfg.checkpoint,
        )

        png_path = images_dir / f"{draft.slug}.png"
        success = False
        for attempt in range(2):
            try:
                png_bytes = render(comfy_cfg.base_url, workflow, float(comfy_cfg.timeout_seconds))
                png_path.write_bytes(png_bytes)
                update_draft(
                    conn,
                    draft.id,  # type: ignore[arg-type]
                    image_path=str(png_path),
                    status=DraftStatus.image_ready.value,
                )
                logger.info("imagery: saved %s", png_path)
                success = True
                break
            except Exception as e:
                if attempt == 0:
                    logger.warning("imagery: render attempt 1 failed for %r: %s — retrying", draft.title, e)
                else:
                    logger.error("imagery: render failed for %r after retry: %s", draft.title, e)
                    update_draft(
                        conn,
                        draft.id,  # type: ignore[arg-type]
                        status=DraftStatus.failed.value,
                        error_message=str(e),
                    )
