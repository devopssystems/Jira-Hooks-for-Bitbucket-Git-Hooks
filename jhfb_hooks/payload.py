"""Build the JSON payload sent to the Process Guardian endpoint."""

from __future__ import annotations

import json
from typing import Literal

from .git import CommitInfo

TRIGGER_COMMIT = "COMMIT"
TRIGGER_PUSH = "PUSH"
TriggerType = Literal["COMMIT", "PUSH"]


def build_payload(
    commits: list[CommitInfo],
    branch: str | None,
    trigger_type: TriggerType,
    locale: str = "en-US",
) -> str:
    """Serialise *commits* and *branch* to the JSON string expected by the endpoint.

    The LocalCheckEndpoint expects a single strict payload shape for both
    commit-msg and pre-push hooks.

    Args:
        commits: Commits to validate.
        branch:  Branch name, or ``None`` when no branch context is available.
        trigger_type: ``COMMIT`` for commit-msg or ``PUSH`` for pre-push.
        locale:  BCP-47 locale tag used for localised rule messages.

    Returns:
        A compact JSON string ready to be sent as the request body.
    """
    if trigger_type not in (TRIGGER_COMMIT, TRIGGER_PUSH):
        raise ValueError(f"Unsupported local check trigger type: {trigger_type}")
    data: dict[str, object] = {
        "commits": [c.to_dict() for c in commits],
        "branchName": branch or "",
        "locale": locale,
        "triggerType": trigger_type,
    }
    return json.dumps(data, separators=(",", ":"))
