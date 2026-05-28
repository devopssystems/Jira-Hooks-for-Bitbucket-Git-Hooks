"""Display constants for the ResultPrinter: icons, styles, and layout."""

from __future__ import annotations

import re as _re

SYSTEM_SOURCES: frozenset[str] = frozenset({"JIRA_CONNECTION", "LICENSE"})

STATUS_ICON: dict[str, str] = {
    "ERROR":     "✗",
    "WARNING":   "!",
    "INFO":      "i",
    "SUCCESS":   "✓",
    "MATCH":     "✓",
    "NOT_MATCH": "✗",
}

RESULT_ICON: dict[str, str] = {
    "PASS":  "✓",
    "BLOCK": "✗",
    "SKIP":  "~",
}

STATUS_RICH_STYLE: dict[str, str] = {
    "ERROR":     "red",
    "WARNING":   "yellow",
    "INFO":      "cyan",
    "SUCCESS":   "green",
    "MATCH":     "green",
    "NOT_MATCH": "yellow",
}

RESULT_RICH_STYLE: dict[str, str] = {
    "PASS": "green",
    "BLOCK": "red",
    "SKIP":  "dim",
}

STATUS_ICON_RICH: dict[str, str] = {
    "ERROR":     "[red]✗[/red]",
    "WARNING":   "[yellow]![/yellow]",
    "INFO":      "[cyan]i[/cyan]",
    "SUCCESS":   "[green]✓[/green]",
    "MATCH":     "[green]✓[/green]",
    "NOT_MATCH": "[yellow]✗[/yellow]",
}

RESULT_ICON_RICH: dict[str, str] = {
    "PASS":  "[green]✓[/green]",
    "BLOCK": "[red]✗[/red]",
    "SKIP":  "[dim]~[/dim]",
}

CONTEXT_TO_SECTION: dict[str, str] = {
    "COMMIT":              "COMMITS",
    "COMMITS":             "COMMITS",
    "BRANCH_SOURCE":       "BRANCH",
    "BRANCH_DESTINATION":  "BRANCH",
    "PR_TITLE":            "TITLE",
    "PR_DESCRIPTION":      "DESCRIPTION",
    "GLOBAL":              "GLOBAL",
    "SYSTEM":              "GLOBAL",
}

SECTION_ORDER: list[str] = ["BRANCH", "TITLE", "DESCRIPTION", "COMMITS"]

SEPARATOR = "─" * 56
CATEGORY_COL_WIDTH = 12           # wide enough for [CONVENTION] (12 chars)
CHECK_MSG_INDENT   = " " * (4 + CATEGORY_COL_WIDTH + 1)   # 17 spaces — branch/title/description
COMMITS_MSG_INDENT = " " * (8 + CATEGORY_COL_WIDTH + 1)   # 21 spaces — inside a commit block
COMMIT_HASH_RE     = _re.compile(r'^[0-9a-f]{7,}$', _re.IGNORECASE)
