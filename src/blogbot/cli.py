import typer

app = typer.Typer(name="blogbot", help="BlogBotBob — multi-agent blog content pipeline.")


@app.command()
def version() -> None:
    """Show blogbot version."""
    typer.echo("blogbotbob 0.1.0")


if __name__ == "__main__":
    app()
