class PipelineHalt(Exception):
    """Raised to stop the pipeline with a user-facing message (not a traceback)."""
