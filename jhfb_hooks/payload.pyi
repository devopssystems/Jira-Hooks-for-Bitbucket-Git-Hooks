from typing import Literal

from .git import CommitInfo

TRIGGER_COMMIT: Literal["COMMIT"]
TRIGGER_PUSH: Literal["PUSH"]
TriggerType = Literal["COMMIT", "PUSH"]

def build_payload(
    commits: list[CommitInfo],
    branch: str | None,
    trigger_type: TriggerType,
    locale: str = "en-US",
) -> str: ...
