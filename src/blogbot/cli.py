import sys
import logging

import typer

from blogbot.config import load_config, load_secrets
from blogbot.llm.router import healthcheck as _healthcheck

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = typer.Typer(name="blogbot", help="BlogBotBob — multi-agent blog content pipeline.")


@app.command()
def version() -> None:
    """Show blogbot version."""
    typer.echo("blogbotbob 0.1.0")


@app.command()
def healthcheck() -> None:
    """Check connectivity to Ollama and Anthropic."""
    config = load_config()
    secrets = load_secrets()
    results = _healthcheck(config, secrets)
    typer.echo(f"ollama:    {results['ollama']}")
    typer.echo(f"anthropic: {results['anthropic']}")


@app.command()
def scrape() -> None:
    """Fetch topics from all enabled sources and upsert into DB."""
    from blogbot.db import get_conn, init_db
    from blogbot.agents.scraper import run_scraper

    config = load_config()
    secrets = load_secrets()
    conn = get_conn()
    init_db(conn)

    report = run_scraper(conn, config, secrets)
    typer.echo(f"new={report.new_topics}  dup={report.duplicates}  errors={len(report.errors)}")
    for src, msg in report.errors:
        typer.echo(f"  ERROR [{src}] {msg}")

    enabled_sources = sum([
        config.sources.rss.enabled,
        config.sources.hackernews.enabled,
        config.sources.reddit.enabled,
        config.sources.linkedin.enabled,
        config.sources.twitter.enabled,
    ])
    if enabled_sources == 0:
        typer.echo("No sources enabled. Enable at least one source in config.yaml.", err=True)
        raise typer.Exit(code=1)
    # Sources that actually attempted a fetch (not just enabled) minus errored ones
    successful_sources = enabled_sources - len(report.errors)
    if successful_sources <= 0 and report.errors:
        typer.echo("All enabled sources failed.", err=True)
        raise typer.Exit(code=1)


@app.command()
def analyze() -> None:
    """Synthesize content angles from scraped topics."""
    from blogbot.db import get_conn, init_db, start_run
    from blogbot.agents import PipelineHalt
    from blogbot.agents.analysis import run_analysis
    from blogbot.llm.base import LLMError

    config = load_config()
    secrets = load_secrets()
    conn = get_conn()
    init_db(conn)
    run_id = start_run(conn)

    try:
        angles = run_analysis(conn, config, secrets, run_id)
    except LLMError as e:
        msg = str(e)
        if "is empty" in msg or "not set" in msg:
            typer.echo(f"Config error: {msg}  run: blogbot setup", err=True)
        else:
            typer.echo(f"LLM error: {msg}", err=True)
        raise typer.Exit(code=1)
    except PipelineHalt as e:
        typer.echo(f"Pipeline halted: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"{'Pri':>3}  {'Topics':>6}  Title")
    typer.echo("-" * 60)
    for angle in sorted(angles, key=lambda a: a.priority):
        import json as _json
        tids = _json.loads(angle.topic_ids)
        typer.echo(f"{angle.priority:>3}  {len(tids):>6}  {angle.title}")


@app.command()
def generate(run_id: str = typer.Option("", help="Run ID (defaults to latest run)")) -> None:
    """Generate blog post drafts from analyzed angles."""
    from blogbot.db import get_conn, init_db
    from blogbot.agents import PipelineHalt
    from blogbot.agents.generation import run_generation
    from blogbot.llm.base import LLMError
    from blogbot.config import MissingSecretError

    config = load_config()
    secrets = load_secrets()
    conn = get_conn()
    init_db(conn)

    if not run_id:
        row = conn.execute("SELECT id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        if not row:
            typer.echo("No runs found. Run: blogbot analyze", err=True)
            raise typer.Exit(code=1)
        run_id = row["id"]

    try:
        draft_ids = run_generation(conn, config, secrets, run_id)
    except MissingSecretError as e:
        typer.echo(f"{e}  run: blogbot setup", err=True)
        raise typer.Exit(code=1)
    except LLMError as e:
        typer.echo(f"LLM error: {e}  run: blogbot setup", err=True)
        raise typer.Exit(code=1)
    except PipelineHalt as e:
        typer.echo(f"Pipeline halted: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Drafts generated: {len(draft_ids)}")


@app.command()
def panel(run_id: str = typer.Option("", help="Run ID (defaults to latest run)")) -> None:
    """Score drafts with audience persona panel and select top-30%."""
    from blogbot.db import get_conn, init_db
    from blogbot.agents import PipelineHalt
    from blogbot.agents.panel import run_panel
    from blogbot.llm.base import LLMError

    config = load_config()
    secrets = load_secrets()
    conn = get_conn()
    init_db(conn)

    if not run_id:
        row = conn.execute("SELECT id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        if not row:
            typer.echo("No runs found.", err=True)
            raise typer.Exit(code=1)
        run_id = row["id"]

    try:
        report = run_panel(conn, config, secrets, run_id)
    except LLMError as e:
        typer.echo(f"LLM error: {e}  run: blogbot setup", err=True)
        raise typer.Exit(code=1)
    except PipelineHalt as e:
        typer.echo(f"Pipeline halted: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"{'Score':>6}  {'Verdict':<10}  Title")
    typer.echo("-" * 70)
    for v in report.verdicts:
        typer.echo(f"{v.score:>6.1f}  {v.verdict:<10}  {v.title}")
    typer.echo(f"\nSelected: {report.k}")


@app.command()
def imagery(run_id: str = typer.Option("", help="Run ID (defaults to latest run)")) -> None:
    """Generate header images for selected drafts via ComfyUI."""
    from blogbot.db import get_conn, init_db, drafts_by_status
    from blogbot.models import DraftStatus
    from blogbot.agents import PipelineHalt
    from blogbot.agents.imagery import run_imagery
    from blogbot.llm.base import LLMError

    config = load_config()
    secrets = load_secrets()
    conn = get_conn()
    init_db(conn)

    if not run_id:
        row = conn.execute("SELECT id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        if not row:
            typer.echo("No runs found.", err=True)
            raise typer.Exit(code=1)
        run_id = row["id"]

    try:
        run_imagery(conn, config, secrets, run_id)
    except LLMError as e:
        typer.echo(f"LLM error: {e}  run: blogbot setup", err=True)
        raise typer.Exit(code=1)
    except PipelineHalt as e:
        typer.echo(f"Pipeline halted: {e}", err=True)
        raise typer.Exit(code=1)

    ready = drafts_by_status(conn, DraftStatus.image_ready, run_id=run_id)
    for d in ready:
        typer.echo(f"  {d.image_path}")
    typer.echo(f"Images ready: {len(ready)}")


if __name__ == "__main__":
    app()
