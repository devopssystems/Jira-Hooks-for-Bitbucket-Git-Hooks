"""Load JHFB hook settings from environment variables or a .env-style file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet

from .i18n import normalize_locale
from .output_level import DEFAULT_PRINT_COMPONENTS, DEFAULT_PRINT_CONFIG, OutputComponent, OutputConfig, resolve_output_components
from .severity_filter import SeverityFilter

_ENV_KEYS = (
    "JHFB_ENDPOINT",
    "JHFB_SECRET",
    "JHFB_PRINT_SUMMARY",
    "JHFB_PRINT_RULE_TITLE",
    "JHFB_PRINT_RULE_META",
    "JHFB_PRINT_RULE_SUMMARY",
    "JHFB_PRINT_RULE_DETAIL",
    "JHFB_PRINT_CONDITIONS",
    "JHFB_SEVERITY_FILTER",
    "JHFB_LOCALE",
    "JHFB_RICH_OUTPUT",
)


def _default_output_levels() -> FrozenSet[OutputComponent]:
    return frozenset(DEFAULT_PRINT_COMPONENTS)


@dataclass(frozen=True)
class CommitCheckConfig:
    """Immutable configuration for the local JHFB check endpoint."""

    url: str
    secret: str
    output_levels: FrozenSet[OutputComponent] = field(default_factory=_default_output_levels)
    output_config: OutputConfig = field(default=DEFAULT_PRINT_CONFIG)
    severity_filter: SeverityFilter = field(default=SeverityFilter.SUCCESS)
    locale: str = "en-US"
    show_conditions: bool = False
    rich_output: bool = True


class ConfigNotFoundError(FileNotFoundError):
    """Raised when the .env config file does not exist."""


class ConfigMissingKeyError(KeyError):
    """Raised when a required key is absent from the config file."""


class ConfigInvalidValueError(ValueError):
    """Raised when a config value is present but invalid."""


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.lower() not in {"0", "false", "no"}


def _parse_severity_filter(value: str | None) -> SeverityFilter:
    severity_name = (value or "SUCCESS").upper()
    try:
        return SeverityFilter.__members__[severity_name]
    except KeyError as exc:
        raise ConfigInvalidValueError(
            "Invalid value for JHFB_SEVERITY_FILTER. Expected one of: "
            + ", ".join(SeverityFilter.__members__.keys())
        ) from exc


def load_config(env_file: Path) -> CommitCheckConfig:
    """Return a config resolved from environment variables and *env_file*.

    Resolution order:
    1. env file
    2. environment variables override file values
    """
    values: dict[str, str] = {}

    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    elif "JHFB_ENDPOINT" not in os.environ:
        raise ConfigNotFoundError(f"Config file not found: {env_file}")

    for key in _ENV_KEYS:
        env_val = os.environ.get(key)
        if env_val is not None:
            values[key] = env_val

    try:
        url = values["JHFB_ENDPOINT"]
        secret = values["JHFB_SECRET"]
    except KeyError as exc:
        raise ConfigMissingKeyError(f"Missing required key {exc} in {env_file}") from exc

    output_config = OutputConfig(
        output_summary=_parse_bool(values.get("JHFB_PRINT_SUMMARY"), default=True),
        rule_title=_parse_bool(values.get("JHFB_PRINT_RULE_TITLE"), default=True),
        rule_meta=_parse_bool(values.get("JHFB_PRINT_RULE_META"), default=False),
        rule_summary=_parse_bool(values.get("JHFB_PRINT_RULE_SUMMARY"), default=False),
        rule_detail=_parse_bool(values.get("JHFB_PRINT_RULE_DETAIL"), default=True),
    )
    output_levels = resolve_output_components(output_config)

    severity_filter = _parse_severity_filter(values.get("JHFB_SEVERITY_FILTER"))

    return CommitCheckConfig(
        url=url,
        secret=secret,
        output_levels=output_levels,
        output_config=output_config,
        severity_filter=severity_filter,
        locale=normalize_locale(values.get("JHFB_LOCALE", "en-US")),
        show_conditions=_parse_bool(values.get("JHFB_PRINT_CONDITIONS"), default=False),
        rich_output=_parse_bool(values.get("JHFB_RICH_OUTPUT"), default=True),
    )
