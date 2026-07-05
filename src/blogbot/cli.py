import typer

from blogbot.config import load_config, load_secrets
from blogbot.llm.router import healthcheck as _healthcheck

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


if __name__ == "__main__":
    app()
