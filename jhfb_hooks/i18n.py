"""Internal wrapper around python-i18n for local hook output."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import i18n # pyright: ignore[reportMissingTypeStubs]

DEFAULT_LOCALE = "en-US"

_LOCALE_ALIASES: dict[str, str] = {
    "en": "en-US",
    "en-us": "en-US",
    "en_us": "en-US",
    "de": "de-DE",
    "de-de": "de-DE",
    "de_de": "de-DE",
}

_SOURCE_KEY_BY_CODE: dict[str, str] = {
    "ISSUE_KEY": "issue_key",
    "JQL": "jql",
    "CONSISTENCY": "consistency",
    "NAMING": "naming",
    "BRANCH_CONDITION": "branch_condition",
    "PULLREQUEST_CONDITION": "pullrequest_condition",
    "JIRA_CONNECTION": "jira_connection",
    "LICENSE": "license",
    "CONDITION": "condition",
}

_SECTION_KEY_BY_CODE: dict[str, str] = {
    "BRANCH": "branch",
    "TITLE": "title",
    "DESCRIPTION": "description",
    "COMMITS": "commits",
}

_LOCALES_DIR = str(Path(__file__).resolve().parent / "locales")
load_path = cast(list[str], i18n.load_path)
if _LOCALES_DIR not in load_path:
    load_path.append(_LOCALES_DIR)
i18n.set("file_format", "json") # pyright: ignore[reportUnknownMemberType]
i18n.set("filename_format", "{locale}.{format}") # pyright: ignore[reportUnknownMemberType]
i18n.set("skip_locale_root_data", True) # pyright: ignore[reportUnknownMemberType]
i18n.set("fallback", DEFAULT_LOCALE) # pyright: ignore[reportUnknownMemberType]


def normalize_locale(locale: str | None) -> str:
    """Return a supported locale tag for local hook output."""
    if locale is None:
        return DEFAULT_LOCALE
    normalized = locale.strip()
    if not normalized:
        return DEFAULT_LOCALE
    return _LOCALE_ALIASES.get(normalized.lower(), normalized)


def translate(locale: str | None, key: str, **kwargs: object) -> str:
    """Translate *key* for *locale* and interpolate *kwargs*."""
    return cast(str, i18n.t(f"localHook.{key}", locale=normalize_locale(locale), **kwargs)) # pyright: ignore[reportUnknownMemberType]


def source_label(locale: str | None, source: str) -> str:
    """Return a localized label for a fact source."""
    source_key = _SOURCE_KEY_BY_CODE.get(source)
    if source_key is None:
        return source
    return translate(locale, f"sources.{source_key}")


def section_label(locale: str | None, section: str) -> str:
    """Return a localized label for a section heading."""
    section_key = _SECTION_KEY_BY_CODE.get(section)
    if section_key is None:
        return section.title()
    return translate(locale, f"sections.{section_key}")
