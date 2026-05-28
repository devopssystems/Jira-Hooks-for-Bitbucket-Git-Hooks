"""Parse the translated Process Guardian endpoint response."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

RESULT_BLOCK = "BLOCK"
RESULT_PASS = "PASS"
RESULT_UNKNOWN = "UNKNOWN"


def _empty_dict_list() -> list[dict[str, object]]:
    return []


@dataclass(frozen=True)
class CheckResult:
    """Parsed result returned by the Process Guardian endpoint."""

    result: str
    rule_validations: list[dict[str, object]] = field(default_factory=_empty_dict_list)
    error_validations: list[dict[str, object]] = field(default_factory=_empty_dict_list)

    def is_blocked(self) -> bool:
        """Return ``True`` when the endpoint decided to block the commit/push."""
        return self.result == RESULT_BLOCK


def _extract_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    for item in cast(list[object], value):
        if isinstance(item, dict):
            result.append(item)  # type: ignore[arg-type]
    return result


def parse_response(data: dict[str, object]) -> CheckResult:
    """Build a :class:`CheckResult` from the raw response dict."""
    rule_validations = _extract_dicts(data.get("ruleValidations"))
    error_validations = _extract_dicts(data.get("errorValidations"))
    return CheckResult(
        result=str(data.get("result", RESULT_UNKNOWN)),
        rule_validations=rule_validations,
        error_validations=error_validations,
    )

