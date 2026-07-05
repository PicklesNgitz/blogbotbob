from __future__ import annotations

from typing import Protocol

from blogbot.models import Topic


class SourceError(Exception):
    """Raised when a source adapter fails."""


class Source(Protocol):
    name: str

    def fetch(self) -> list[Topic]: ...
