"""Git helper functions for reading commits, branch names, and author info."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

ZERO_SHA = "0000000000000000000000000000000000000000"

# Field separator (ASCII unit-separator) and record separator used in git log output.
_FIELD_SEP = "\x1f"
_RECORD_SEP = "\x1e"


@dataclass(frozen=True)
class CommitInfo:
    """Represents a single git commit relevant for Process Guardian validation."""

    hash: str
    message: str
    author_display_name: str

    def to_dict(self) -> dict[str, str]:
        """Return the dict representation expected by the endpoint payload."""
        return {
            "hash": self.hash,
            "message": self.message,
            "authorDisplayName": self.author_display_name,
        }


def get_commits_for_range(range_spec: str) -> list[CommitInfo]:
    """Return all commits covered by *range_spec*.

    *range_spec* can be:
    - A revision range such as ``"abc123..def456"`` (commits between two SHAs)
    - A single SHA (only that commit)

    Multi-line commit messages are handled correctly.
    """
    result = subprocess.run(
        [
            "git", "log",
            f"--format=%H{_FIELD_SEP}%B{_FIELD_SEP}%aN{_RECORD_SEP}",
            range_spec,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    commits: list[CommitInfo] = []
    for record in result.stdout.split(_RECORD_SEP):
        record = record.strip()
        if not record:
            continue
        parts = record.split(_FIELD_SEP, 2)
        if len(parts) == 3:
            commits.append(
                CommitInfo(
                    hash=parts[0].strip(),
                    message=parts[1].strip(),
                    author_display_name=parts[2].strip(),
                )
            )
    return commits


def get_commits_not_on_remotes(revision: str = "HEAD") -> list[CommitInfo]:
    """Return commits reachable from *revision* that are not on any remote ref."""
    result = subprocess.run(
        [
            "git", "log",
            f"--format=%H{_FIELD_SEP}%B{_FIELD_SEP}%aN{_RECORD_SEP}",
            revision,
            "--not",
            "--remotes",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    commits: list[CommitInfo] = []
    for record in result.stdout.split(_RECORD_SEP):
        record = record.strip()
        if not record:
            continue
        parts = record.split(_FIELD_SEP, 2)
        if len(parts) == 3:
            commits.append(
                CommitInfo(
                    hash=parts[0].strip(),
                    message=parts[1].strip(),
                    author_display_name=parts[2].strip(),
                )
            )
    return commits


def get_current_branch() -> str:
    """Return the short branch name of HEAD, or an empty string on detached HEAD."""
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def get_author() -> str:
    """Return the configured ``user.name`` from git config, or an empty string."""
    result = subprocess.run(
        ["git", "config", "user.name"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def abbrev_ref(ref: str) -> str:
    """Resolve a full git ref (e.g. ``refs/heads/main``) to its short name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def read_commit_message(path: Path) -> str:
    """Read the commit message from *path*, stripping trailing whitespace."""
    return path.read_text(encoding="utf-8").rstrip()
