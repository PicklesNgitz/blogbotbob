import logging
import logging.handlers
from pathlib import Path

import typer

from blogbot.config import load_config, load_secrets
from blogbot.llm.router import healthcheck as _healthcheck

_LOG_FMT = "%(levelname)s %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT)

app = typer.Typer(name="blogbot", help="BlogBotBob — multi-agent blog content pipeline.")
queue_app = typer.Typer(help="Human approval queue.")
app.add_typer(queue_app, name="queue")


def _setup_file_logging() -> None:
    log_dir = Path("data")
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        log_dir / "blogbot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_LOG_FMT))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in root.handlers:
        if h.level == logging.NOTSET:
            h.setLevel(logging.INFO)
    root.addHandler(fh)
    for noisy in ("httpcore", "httpx", "urllib3", "praw"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _get_latest_run_id(conn) -> str:
    row = conn.execute("SELECT id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
    if not row:
        typer.echo("No runs found.", err=True)
        raise typer.Exit(code=1)
    return row["id"]


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------

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
    import json as _json

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
        run_id = _get_latest_run_id(conn)

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
        run_id = _get_latest_run_id(conn)

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
    from blogbot.db import get_conn, init_db, drafts_by_status, update_draft
    from blogbot.models import DraftStatus
    from blogbot.agents import PipelineHalt
    from blogbot.agents.imagery import run_imagery
    from blogbot.llm.base import LLMError

    config = load_config()
    secrets = load_secrets()
    conn = get_conn()
    init_db(conn)

    if not run_id:
        run_id = _get_latest_run_id(conn)

    try:
        run_imagery(conn, config, secrets, run_id)
    except LLMError as e:
        typer.echo(f"LLM error: {e}  run: blogbot setup", err=True)
        raise typer.Exit(code=1)
    except PipelineHalt as e:
        typer.echo(f"Pipeline halted: {e}", err=True)
        raise typer.Exit(code=1)

    # Auto-enqueue image_ready → pending_approval
    ready = drafts_by_status(conn, DraftStatus.image_ready, run_id=run_id)
    for d in ready:
        update_draft(conn, d.id, status=DraftStatus.pending_approval.value)  # type: ignore[arg-type]
        typer.echo(f"  queued: {d.image_path}")
    typer.echo(f"Images ready, enqueued for approval: {len(ready)}")


# ---------------------------------------------------------------------------
# Queue sub-commands
# ---------------------------------------------------------------------------

@queue_app.command("list")
def queue_list() -> None:
    """List drafts pending human approval."""
    from blogbot.db import get_conn, init_db, drafts_by_status
    from blogbot.models import DraftStatus

    conn = get_conn()
    init_db(conn)
    drafts = drafts_by_status(conn, DraftStatus.pending_approval)
    if not drafts:
        typer.echo("Queue empty.")
        return
    typer.echo(f"{'ID':>4}  {'Score':>6}  {'Created':<20}  {'Image':<30}  Title")
    typer.echo("-" * 100)
    for d in drafts:
        score = f"{d.panel_score:.1f}" if d.panel_score is not None else "   —"
        img = (d.image_path or "")[-28:]
        typer.echo(f"{d.id:>4}  {score:>6}  {d.created_at:<20}  {img:<30}  {d.title}")


@queue_app.command("show")
def queue_show(draft_id: int = typer.Argument(..., help="Draft ID")) -> None:
    """Show full markdown and panel votes for a pending draft."""
    from blogbot.db import get_conn, init_db, get_draft, votes_for_draft
    from blogbot.models import DraftStatus

    conn = get_conn()
    init_db(conn)
    try:
        draft = get_draft(conn, draft_id)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)

    if draft.status != DraftStatus.pending_approval:
        typer.echo(f"Draft {draft_id} is not pending approval (status: {draft.status.value})", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"=== Draft {draft_id}: {draft.title} ===")
    typer.echo(f"Image: {draft.image_path or 'none'}")
    typer.echo(f"Score: {draft.panel_score}")
    typer.echo()
    typer.echo(draft.markdown)
    typer.echo()
    typer.echo("--- Panel votes ---")
    for vote in votes_for_draft(conn, draft_id):
        typer.echo(f"  {vote.persona:<20} {vote.score:>4.1f}  {vote.critique[:80]}")


@queue_app.command("approve")
def queue_approve(draft_id: int = typer.Argument(..., help="Draft ID")) -> None:
    """Approve a pending draft for publishing."""
    from blogbot.db import get_conn, init_db, get_draft, update_draft
    from blogbot.models import DraftStatus

    conn = get_conn()
    init_db(conn)
    try:
        draft = get_draft(conn, draft_id)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)

    if draft.status != DraftStatus.pending_approval:
        typer.echo(
            f"Draft {draft_id} cannot be approved — status is '{draft.status.value}', "
            "must be 'pending_approval'.",
            err=True,
        )
        raise typer.Exit(code=1)

    update_draft(conn, draft_id, status=DraftStatus.approved.value)
    typer.echo(f"Draft {draft_id} '{draft.title}' approved.")


@queue_app.command("reject")
def queue_reject(
    draft_id: int = typer.Argument(..., help="Draft ID"),
    reason: str = typer.Option("", help="Rejection reason"),
) -> None:
    """Reject a pending draft."""
    from blogbot.db import get_conn, init_db, get_draft, update_draft
    from blogbot.models import DraftStatus

    conn = get_conn()
    init_db(conn)
    try:
        draft = get_draft(conn, draft_id)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)

    if draft.status != DraftStatus.pending_approval:
        typer.echo(
            f"Draft {draft_id} cannot be rejected — status is '{draft.status.value}'.",
            err=True,
        )
        raise typer.Exit(code=1)

    err_msg = f"rejected by user: {reason}" if reason else "rejected by user"
    update_draft(conn, draft_id, status=DraftStatus.rejected.value, error_message=err_msg)
    typer.echo(f"Draft {draft_id} '{draft.title}' rejected. Reason: {reason or '(none)'}")


@queue_app.command("edit")
def queue_edit(draft_id: int = typer.Argument(..., help="Draft ID")) -> None:
    """Dump draft markdown to a temp file for editing."""
    from blogbot.db import get_conn, init_db, get_draft
    from blogbot.models import DraftStatus

    conn = get_conn()
    init_db(conn)
    try:
        draft = get_draft(conn, draft_id)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)

    if draft.status != DraftStatus.pending_approval:
        typer.echo(f"Draft {draft_id} is not pending approval (status: {draft.status.value})", err=True)
        raise typer.Exit(code=1)

    edit_path = Path("data") / f"edit-{draft_id}.md"
    edit_path.parent.mkdir(parents=True, exist_ok=True)
    edit_path.write_text(draft.markdown, encoding="utf-8")
    typer.echo(f"Edit file: {edit_path}")
    typer.echo(f"When done: blogbot queue save {draft_id}")


@queue_app.command("save")
def queue_save(draft_id: int = typer.Argument(..., help="Draft ID")) -> None:
    """Save edits from temp file back to the draft."""
    from blogbot.db import get_conn, init_db, get_draft, update_draft
    from blogbot.models import DraftStatus
    import frontmatter as _fm

    conn = get_conn()
    init_db(conn)
    try:
        draft = get_draft(conn, draft_id)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)

    if draft.status != DraftStatus.pending_approval:
        typer.echo(f"Draft {draft_id} is not pending approval (status: {draft.status.value})", err=True)
        raise typer.Exit(code=1)

    edit_path = Path("data") / f"edit-{draft_id}.md"
    if not edit_path.exists():
        typer.echo(f"Edit file not found: {edit_path}. Run: blogbot queue edit {draft_id}", err=True)
        raise typer.Exit(code=1)

    new_text = edit_path.read_text(encoding="utf-8")
    try:
        post = _fm.loads(new_text)
        missing = [k for k in ("title", "description", "tags") if k not in post.metadata]
        if missing:
            typer.echo(f"Frontmatter missing required keys: {missing}", err=True)
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Frontmatter parse error: {e}", err=True)
        raise typer.Exit(code=1)

    update_draft(conn, draft_id, markdown=new_text, status=DraftStatus.pending_approval.value)
    edit_path.unlink(missing_ok=True)
    typer.echo(f"Draft {draft_id} updated and still pending approval.")


@app.command()
def publish(run_id: str = typer.Option("", help="Run ID (defaults to all approved drafts)")) -> None:
    """Publish approved drafts to WordPress."""
    from blogbot.db import get_conn, init_db, drafts_by_status
    from blogbot.models import DraftStatus
    from blogbot.agents import PipelineHalt
    from blogbot.publish.wordpress import run_publish

    config = load_config()
    secrets = load_secrets()
    conn = get_conn()
    init_db(conn)

    run_id_arg = run_id if run_id else None

    # Check for approved drafts before calling run_publish
    approved = drafts_by_status(conn, DraftStatus.approved, run_id=run_id_arg)
    if not approved:
        typer.echo("Nothing approved to publish.")
        return

    try:
        results = run_publish(conn, config, secrets, run_id=run_id_arg)
    except PipelineHalt as e:
        typer.echo(f"Pipeline halted: {e}  run: blogbot setup", err=True)
        raise typer.Exit(code=1)

    for wp_id, wp_url in results:
        typer.echo(f"published: {wp_url}")
    typer.echo(f"Total published: {len(results)}")


@app.command()
def run() -> None:
    """Run the full pipeline: scrape → analyze → generate → panel → imagery → enqueue."""
    import traceback
    from blogbot.db import get_conn, init_db, start_run, finish_run, drafts_by_status, update_draft
    from blogbot.models import DraftStatus
    from blogbot.agents import PipelineHalt
    from blogbot.agents.scraper import run_scraper
    from blogbot.agents.analysis import run_analysis
    from blogbot.agents.generation import run_generation
    from blogbot.agents.panel import run_panel
    from blogbot.agents.imagery import run_imagery
    from blogbot.llm.base import LLMError
    from blogbot.config import MissingSecretError

    _setup_file_logging()
    config = load_config()
    secrets = load_secrets()
    conn = get_conn()
    init_db(conn)
    run_id = start_run(conn)
    logger = logging.getLogger("blogbot.run")
    logger.info("Run %s started", run_id)

    stage = "init"
    try:
        # 1. Scrape
        stage = "scrape"
        logger.info("--- scrape ---")
        scrape_report = run_scraper(conn, config, secrets)
        enabled = sum([
            config.sources.rss.enabled, config.sources.hackernews.enabled,
            config.sources.reddit.enabled, config.sources.linkedin.enabled,
            config.sources.twitter.enabled,
        ])
        if enabled > 0 and len(scrape_report.errors) >= enabled:
            finish_run(conn, run_id, stage_reached=stage, notes="all sources errored")
            typer.echo("All enabled sources failed — run: blogbot setup", err=True)
            raise typer.Exit(code=1)

        # 2. Analyze
        stage = "analyze"
        logger.info("--- analyze ---")
        angles = run_analysis(conn, config, secrets, run_id)

        # 3. Generate
        stage = "generate"
        logger.info("--- generate ---")
        draft_ids = run_generation(conn, config, secrets, run_id)

        # 4. Panel
        stage = "panel"
        logger.info("--- panel ---")
        panel_report = run_panel(conn, config, secrets, run_id)

        # 5. Imagery
        stage = "imagery"
        logger.info("--- imagery ---")
        run_imagery(conn, config, secrets, run_id)

        # 6. Enqueue
        stage = "enqueue"
        ready = drafts_by_status(conn, DraftStatus.image_ready, run_id=run_id)
        for d in ready:
            update_draft(conn, d.id, status=DraftStatus.pending_approval.value)  # type: ignore[arg-type]

        queued = len(ready)
        finish_run(conn, run_id, stage_reached="enqueued",
                   notes=f"angles={len(angles)} drafts={len(draft_ids)} selected={panel_report.k} queued={queued}")

        typer.echo(f"\nRun {run_id} complete.")
        typer.echo(f"topics: {scrape_report.new_topics} new | angles: {len(angles)} | "
                   f"drafts: {len(draft_ids)} | selected: {panel_report.k} | queued: {queued}")
        typer.echo("Next: blogbot queue list")

    except (PipelineHalt, LLMError, MissingSecretError) as e:
        finish_run(conn, run_id, stage_reached=stage, notes=str(e))
        typer.echo(f"Pipeline halted at {stage}: {e}  — run: blogbot setup", err=True)
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        finish_run(conn, run_id, stage_reached=stage, notes=str(e))
        logger.exception("Unexpected error at stage %s", stage)
        typer.echo(f"Unexpected error at {stage}: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Show draft counts by status and last 3 runs."""
    from blogbot.db import get_conn, init_db

    conn = get_conn()
    init_db(conn)

    typer.echo("=== Draft status counts ===")
    rows = conn.execute(
        "SELECT status, COUNT(*) as n FROM drafts GROUP BY status ORDER BY status"
    ).fetchall()
    if not rows:
        typer.echo("  (no drafts)")
    else:
        for row in rows:
            typer.echo(f"  {row['status']:<20} {row['n']}")

    typer.echo("\n=== Last 3 runs ===")
    runs = conn.execute(
        "SELECT id, started_at, finished_at, stage_reached, notes FROM runs "
        "ORDER BY started_at DESC LIMIT 3"
    ).fetchall()
    if not runs:
        typer.echo("  (no runs)")
    else:
        for r in runs:
            finished = r["finished_at"] or "running"
            typer.echo(f"  {r['id'][:8]}  started={r['started_at']}  "
                       f"finished={finished}  stage={r['stage_reached'] or '?'}")


@app.command()
def setup() -> None:
    """First-run setup wizard — configures sources, LLM backends, ComfyUI, WordPress."""
    from blogbot.setup_wizard import run_wizard

    _setup_file_logging()
    run_wizard()


if __name__ == "__main__":
    app()
