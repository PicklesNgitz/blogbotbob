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


if __name__ == "__main__":
    app()
