"""Output component mapping for the ResultPrinter."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import FrozenSet


class OutputComponent(enum.Enum):
    """Internal output components used by the ResultPrinter."""

    DISABLED = "DISABLED"
    SUMMARY = "SUMMARY"
    RULES_TITLE = "RULES_TITLE"
    RULES_META = "RULES_META"
    RULE_SUMMARY = "RULE_SUMMARY"
    RULES_DETAILED = "RULES_DETAILED"


@dataclass(frozen=True)
class OutputConfig:
    output_summary: bool = True
    rule_title: bool = True
    rule_meta: bool = True
    rule_summary: bool = True
    rule_detail: bool = True


DEFAULT_PRINT_CONFIG = OutputConfig()

DEFAULT_PRINT_COMPONENTS: FrozenSet[OutputComponent] = frozenset({
    OutputComponent.SUMMARY,
    OutputComponent.RULES_TITLE,
    OutputComponent.RULES_META,
    OutputComponent.RULE_SUMMARY,
    OutputComponent.RULES_DETAILED,
})


DEFAULT_JHFB_PRINT_CONFIG = DEFAULT_PRINT_CONFIG
DEFAULT_JHFB_PRINT_COMPONENTS = DEFAULT_PRINT_COMPONENTS


def resolve_output_components(config: OutputConfig = DEFAULT_PRINT_CONFIG) -> FrozenSet[OutputComponent]:
    """Map output flags to printer components."""
    effective_rule_title = config.rule_title or config.rule_meta or config.rule_summary
    components: set[OutputComponent] = set()
    if config.output_summary:
        components.add(OutputComponent.SUMMARY)
    if effective_rule_title:
        components.add(OutputComponent.RULES_TITLE)
    if config.rule_meta:
        components.add(OutputComponent.RULES_META)
    if config.rule_summary:
        components.add(OutputComponent.RULE_SUMMARY)
    if config.rule_detail:
        components.add(OutputComponent.RULES_DETAILED)
    if not components:
        return frozenset({OutputComponent.DISABLED})
    return frozenset(components)
