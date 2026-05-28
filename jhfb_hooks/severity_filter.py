"""Severity filter controlling which fact statuses are displayed."""

from __future__ import annotations

import enum


SEVERITY_LEVEL: dict[str, int] = {
    "ERROR":     1,
    "WARNING":   2,
    "NOT_MATCH": 2,
    "INFO":      3,
    "SUCCESS":   4,
    "MATCH":     4,
}


class SeverityFilter(enum.IntEnum):
    """Controls which fact statuses are shown based on minimum severity.

    - ``ERROR``   — only errors.
    - ``WARNING`` — errors + warnings (no info, no success).
    - ``INFO``    — errors + warnings + info (no success).
    - ``SUCCESS`` — all (default).
    """

    ERROR   = 1
    WARNING = 2
    INFO    = 3
    SUCCESS = 4

    def allows(self, status: str) -> bool:
        """Return ``True`` if a fact with *status* should be shown."""
        level = SEVERITY_LEVEL.get(status.upper(), 3)
        return level <= self.value
