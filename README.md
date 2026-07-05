# BlogBotBob

End-to-end editorial automation running locally on your Windows PC. BlogBotBob scrapes trending topics from configurable sources, synthesizes content angles, generates full blog posts using Claude, scores them with a simulated audience panel, generates header images via ComfyUI/SDXL, presents surviving drafts for your approval, then publishes approved posts to WordPress — all on a configurable weekly schedule.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
blogbot setup    # first-run wizard: configures sources, models, and credentials
blogbot run      # execute the full pipeline
```

No manual file editing required. The `blogbot setup` wizard writes `config.yaml` and `.env` for you.

## Pipeline

```
[Scraper] → [Analysis] → [Generation] → [Audience Panel] → [Image] → [Approval] → [Publisher]
   RSS/HN      dedupe/       Claude        persona score      SDXL      CLI queue    WordPress
   Reddit/X    cluster/      drafts        top 30% kept       header    human ok     REST API
   LinkedIn    synthesize
```

## Configuration

All runtime configuration is set by the `blogbot setup` wizard. Key options:

| Setting | Default | Description |
|---|---|---|
| `run.max_publishes_per_run` | 2 | Max posts published per scheduler run |
| `run.panel_top_fraction` | 0.30 | Fraction of drafts that pass audience panel |
| `drafting.posts_per_run` | 6 | Drafts generated per run (before panel cull) |
| `llm.anthropic.model_draft` | `claude-sonnet-4-6` | Claude model for draft generation |
| `wordpress.default_status` | `draft` | WP post status on publish |

## Security

Credentials live only in `.env`, written by the setup wizard, and are never committed to git. The `.gitignore` excludes `.env` and the `data/` directory. See `.env.example` for the list of supported secrets.
