from __future__ import annotations

import logging
from pathlib import Path

import httpx
import typer

from blogbot.config import (
    Config,
    Secrets,
    load_config,
    load_secrets,
    save_config,
    write_env,
)
from blogbot.llm.router import healthcheck

logger = logging.getLogger(__name__)

_SEP = "-" * 60


def _section(title: str) -> None:
    typer.echo(f"\n{_SEP}\n{title}\n{_SEP}")


def _mask(val: str) -> str:
    return f"...{val[-4:]}" if len(val) > 4 else "****"


def run_wizard() -> None:
    config = load_config()
    secrets = load_secrets()
    config_path = Path("config.yaml")
    env_path = Path(".env")

    typer.echo("BlogBotBob Setup Wizard")
    typer.echo("Press Enter to keep current value. Ctrl-C to abort (no changes written).")

    # -----------------------------------------------------------------------
    # 1. Anthropic
    # -----------------------------------------------------------------------
    _section("1 / 6  Anthropic API Key")
    current_key = secrets.ANTHROPIC_API_KEY
    hint = f" (current: {_mask(current_key)})" if current_key else ""
    for attempt in range(3):
        key = typer.prompt(f"ANTHROPIC_API_KEY{hint}", hide_input=True, default=current_key)
        if not key:
            typer.echo("Skipping Anthropic — draft generation will not work until set.")
            break
        # Validate with 1-token ping
        try:
            from blogbot.llm.anthropic_client import AnthropicClient
            client = AnthropicClient(api_key=key, model=config.llm.anthropic.model_draft)
            client.complete(system="ping", user="ping", max_tokens=1)
            write_env({"ANTHROPIC_API_KEY": key}, env_path)
            secrets.ANTHROPIC_API_KEY = key
            typer.echo("Anthropic: OK")
            break
        except Exception as e:
            typer.echo(f"  Error: {e}")
            if attempt == 2:
                typer.echo("3 failures — skipping Anthropic. Re-run blogbot setup to retry.")

    # -----------------------------------------------------------------------
    # 2. Ollama
    # -----------------------------------------------------------------------
    _section("2 / 6  Ollama")
    base_url = typer.prompt("Ollama base URL", default=config.llm.ollama.base_url)
    config.llm.ollama.base_url = base_url

    models: list[str] = []
    for retry in range(2):
        try:
            resp = httpx.get(f"{base_url}/api/tags", timeout=5.0)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            typer.echo(f"Ollama reachable. Installed models: {', '.join(models) or '(none)'}")
            break
        except Exception as e:
            typer.echo(f"  Cannot reach Ollama: {e}")
            if retry == 0 and typer.confirm("  Retry?", default=True):
                continue
            typer.echo("  Skipping Ollama. Run blogbot setup again after starting Ollama.")
            break

    if models:
        for i, m in enumerate(models, 1):
            typer.echo(f"  {i}. {m}")
        for field, label in [("model_analysis", "model_analysis"), ("model_panel", "model_panel")]:
            current = getattr(config.llm.ollama, field)
            hint = f" (current: {current})" if current else ""
            idx_str = typer.prompt(f"Pick number for {label}{hint}", default="")
            if idx_str.strip().isdigit():
                idx = int(idx_str.strip()) - 1
                if 0 <= idx < len(models):
                    setattr(config.llm.ollama, field, models[idx])
            elif not idx_str.strip() and current:
                pass  # keep current

    save_config(config, config_path)

    # -----------------------------------------------------------------------
    # 3. Sources
    # -----------------------------------------------------------------------
    _section("3 / 6  Sources")

    # RSS
    if typer.confirm("Enable RSS feeds?", default=config.sources.rss.enabled):
        config.sources.rss.enabled = True
        feeds: list[str] = list(config.sources.rss.feeds)
        typer.echo("Enter feed URLs one per line (blank to stop):")
        while True:
            url = typer.prompt("  Feed URL", default="")
            if not url:
                break
            import feedparser
            parsed = feedparser.parse(url)
            if parsed.bozo and not parsed.entries:
                if typer.confirm(f"  Warning: could not parse {url}. Keep anyway?", default=False):
                    feeds.append(url)
            else:
                feeds.append(url)
                typer.echo(f"  OK — {len(parsed.entries)} entries found")
        config.sources.rss.feeds = feeds
    else:
        config.sources.rss.enabled = False

    # HackerNews
    config.sources.hackernews.enabled = typer.confirm(
        "Enable HackerNews?", default=config.sources.hackernews.enabled
    )

    # Reddit
    if typer.confirm("Enable Reddit?", default=config.sources.reddit.enabled):
        config.sources.reddit.enabled = True
        subs_str = typer.prompt(
            "Subreddits (comma-separated)", default=",".join(config.sources.reddit.subreddits)
        )
        config.sources.reddit.subreddits = [s.strip() for s in subs_str.split(",") if s.strip()]
        cid = typer.prompt("REDDIT_CLIENT_ID", hide_input=True, default=secrets.REDDIT_CLIENT_ID)
        csec = typer.prompt("REDDIT_CLIENT_SECRET", hide_input=True, default=secrets.REDDIT_CLIENT_SECRET)
        if cid and csec:
            write_env({"REDDIT_CLIENT_ID": cid, "REDDIT_CLIENT_SECRET": csec}, env_path)
    else:
        config.sources.reddit.enabled = False

    # Twitter
    if typer.confirm("Enable Twitter/X?", default=config.sources.twitter.enabled):
        config.sources.twitter.enabled = True
        bearer = typer.prompt("TWITTER_BEARER_TOKEN", hide_input=True, default=secrets.TWITTER_BEARER_TOKEN)
        query = typer.prompt("Search query", default=config.sources.twitter.query)
        config.sources.twitter.query = query
        if bearer:
            write_env({"TWITTER_BEARER_TOKEN": bearer}, env_path)
    else:
        config.sources.twitter.enabled = False

    # LinkedIn always disabled in v1
    typer.echo("LinkedIn: not available in v1 (kept disabled).")

    save_config(config, config_path)

    # -----------------------------------------------------------------------
    # 4. ComfyUI
    # -----------------------------------------------------------------------
    _section("4 / 6  ComfyUI")
    comfy_url = typer.prompt("ComfyUI base URL", default=config.imagery.comfyui.base_url)
    config.imagery.comfyui.base_url = comfy_url

    checkpoints: list[str] = []
    for retry in range(2):
        try:
            resp = httpx.get(f"{comfy_url}/object_info", timeout=10.0)
            resp.raise_for_status()
            info = resp.json()
            ckpt_info = info.get("CheckpointLoaderSimple", {})
            input_info = ckpt_info.get("input", {}).get("required", {})
            ckpt_list = input_info.get("ckpt_name", [None])
            if ckpt_list and isinstance(ckpt_list[0], list):
                checkpoints = ckpt_list[0]
            typer.echo(f"ComfyUI reachable. Checkpoints: {', '.join(checkpoints) or '(none)'}")
            break
        except Exception as e:
            typer.echo(f"  Cannot reach ComfyUI: {e}")
            if retry == 0 and typer.confirm("  Retry?", default=True):
                continue
            typer.echo("  Skipping ComfyUI. Run blogbot setup again after starting ComfyUI.")
            break

    if checkpoints:
        for i, c in enumerate(checkpoints, 1):
            typer.echo(f"  {i}. {c}")
        idx_str = typer.prompt(
            f"Pick checkpoint number (current: {config.imagery.comfyui.checkpoint or 'none'})",
            default="",
        )
        if idx_str.strip().isdigit():
            idx = int(idx_str.strip()) - 1
            if 0 <= idx < len(checkpoints):
                config.imagery.comfyui.checkpoint = checkpoints[idx]

    save_config(config, config_path)

    # -----------------------------------------------------------------------
    # 5. WordPress
    # -----------------------------------------------------------------------
    _section("5 / 6  WordPress")
    if typer.confirm("Configure WordPress publishing?", default=bool(config.wordpress.base_url)):
        for attempt in range(3):
            wp_url = typer.prompt("WordPress site URL (e.g. https://example.com)",
                                  default=config.wordpress.base_url)
            wp_user = typer.prompt("WP_USERNAME", default=secrets.WP_USERNAME)
            wp_pass = typer.prompt("WP_APP_PASSWORD (Application Password)", hide_input=True,
                                   default=secrets.WP_APP_PASSWORD)
            try:
                from blogbot.publish.wordpress import WPClient
                wpc = WPClient(wp_url, wp_user, wp_pass)
                name = wpc.verify()
                config.wordpress.base_url = wp_url
                write_env({"WP_USERNAME": wp_user, "WP_APP_PASSWORD": wp_pass}, env_path)
                typer.echo(f"WordPress: connected as {name}")
                break
            except Exception as e:
                typer.echo(f"  Error: {e}")
                typer.echo("  In wp-admin → Users → Profile → Application Passwords → Add New.")
                if attempt == 2:
                    typer.echo("3 failures — skipping WordPress.")

        cat = typer.prompt("Default category", default=config.wordpress.category)
        config.wordpress.category = cat
        save_config(config, config_path)
    else:
        typer.echo("Skipping WordPress — configure later via blogbot setup.")

    # -----------------------------------------------------------------------
    # 6. Cadence
    # -----------------------------------------------------------------------
    _section("6 / 6  Cadence")
    val = typer.prompt(f"max_publishes_per_run", default=str(config.run.max_publishes_per_run))
    try:
        config.run.max_publishes_per_run = int(val)
    except ValueError:
        pass
    val = typer.prompt(f"posts_per_run (drafts before panel cull)", default=str(config.drafting.posts_per_run))
    try:
        config.drafting.posts_per_run = int(val)
    except ValueError:
        pass
    save_config(config, config_path)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    _section("Setup complete")
    typer.echo("Configuration summary:")
    typer.echo(f"  ANTHROPIC_API_KEY : {'set' if secrets.ANTHROPIC_API_KEY or Path('.env').exists() else 'not set'}")
    typer.echo(f"  Ollama model_analysis : {config.llm.ollama.model_analysis or 'not set'}")
    typer.echo(f"  Ollama model_panel    : {config.llm.ollama.model_panel or 'not set'}")
    typer.echo(f"  ComfyUI checkpoint    : {config.imagery.comfyui.checkpoint or 'not set'}")
    typer.echo(f"  WordPress URL         : {config.wordpress.base_url or 'not set'}")
    typer.echo(f"\nRun: blogbot healthcheck")
    typer.echo("Then: blogbot run")
