from __future__ import annotations

from blogbot.models import Topic
from blogbot.sources.base import SourceError


class LinkedInSource:
    name = "linkedin"

    def fetch(self) -> list[Topic]:
        raise SourceError("linkedin source not implemented in v1 — disable in config.yaml")
