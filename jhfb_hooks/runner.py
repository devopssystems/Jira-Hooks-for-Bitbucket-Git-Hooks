"""High-level API: orchestrates config loading, signing, sending, and result output."""

from __future__ import annotations

import sys
import time
import os
from pathlib import Path

from .client import send_check
from .config import CommitCheckConfig, ConfigInvalidValueError, ConfigMissingKeyError, ConfigNotFoundError, load_config
from .git import CommitInfo, ZERO_SHA, abbrev_ref, get_author, get_commits_not_on_remotes, get_current_branch, read_commit_message
from .i18n import DEFAULT_LOCALE, normalize_locale, translate
from .payload import TRIGGER_COMMIT, TRIGGER_PUSH, TriggerType, build_payload
from .result_printer import ResultPrinter
from .result import parse_response
from .signer import sign_payload


def _load_hook_config_or_exit_zero(hook_dir: Path) -> CommitCheckConfig | None:
    """Load hook config and return ``None`` when the hook should be skipped."""
    return load_config_or_skip(hook_dir)


def _resolve_locale_from_env_file(env_file: Path) -> str:
    locale = os.environ.get("JHFB_LOCALE")
    if locale is not None:
        return normalize_locale(locale)
    if not env_file.exists():
        return DEFAULT_LOCALE
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "JHFB_LOCALE":
            return normalize_locale(value.strip().strip('"').strip("'"))
    return DEFAULT_LOCALE


def run_check(
    commits: list[CommitInfo],
    branch: str | None,
    config: CommitCheckConfig,
    trigger_type: TriggerType,
    locale: str = "en-US",
) -> int:
    """Validate *commits* against the Process Guardian endpoint.

    Builds the payload, signs it, sends the HTTP request, and prints the
    result to stdout/stderr.

    Args:
        commits: The commits to validate.
        branch:  Branch name associated with the commits, or ``None`` if no
                 branch context is available.
        config:  Endpoint URL and HMAC secret.
        trigger_type: ``COMMIT`` for commit-msg or ``PUSH`` for pre-push.
        locale:  BCP-47 locale for localised messages (default ``"en-US"``).


    Returns:
        ``0`` on success (pass or skip), ``1`` when the push/commit is blocked
        or the request fails.
    """
    effective_locale = config.locale if locale == DEFAULT_LOCALE else locale
    payload = build_payload(commits, branch, trigger_type, effective_locale)
    signature = sign_payload(payload, config.secret)
    printer = ResultPrinter(
        output_levels=config.output_levels,
        rich_enabled=config.rich_output,
        severity_filter=config.severity_filter,
        show_conditions=config.show_conditions,
        locale=effective_locale,
    )

    start_time = time.monotonic()
    try:
        status_code, body = send_check(config.url, payload, signature)
    except Exception as exc:  # noqa: BLE001
        printer.print_connection_error(exc)
        return 1
    elapsed = time.monotonic() - start_time

    if status_code != 200:
        printer.print_http_error(status_code, body)
        return 1

    result = parse_response(body)
    printer.print_result(result, len(commits), elapsed)
    return 1 if result.is_blocked() else 0


def load_config_or_skip(hook_dir: Path) -> CommitCheckConfig | None:
    """Load config from ``<hook_dir>/commit-check.env``.

    Returns ``None`` (and prints a warning) when the file is missing so that
    the calling hook can exit with code ``0`` (skip gracefully).
    """
    env_file = hook_dir / "commit-check.env"
    locale = _resolve_locale_from_env_file(env_file)
    try:
        return load_config(env_file)
    except ConfigNotFoundError:
        print(
            translate(locale, "skip_missing_file", env_file=env_file),
            file=sys.stderr,
        )
        return None
    except (ConfigMissingKeyError, ConfigInvalidValueError) as exc:
        print(
            translate(locale, "skip_invalid_config", error=exc),
            file=sys.stderr,
        )
        return None


def _collect_pre_push_commits() -> tuple[list[CommitInfo], str]:
    """Return unique commits for refs being pushed that are not yet on any remote."""
    branch = ""
    commits_by_hash: dict[str, CommitInfo] = {}

    for line in sys.stdin:
        parts = line.rstrip().split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, _remote_ref, _remote_sha = parts
        if local_sha == ZERO_SHA:
            continue
        branch = abbrev_ref(local_ref)
        for commit in get_commits_not_on_remotes(local_sha):
            commits_by_hash.setdefault(commit.hash, commit)

    return list(commits_by_hash.values()), branch


def main_pre_push(hook_dir: Path, locale: str = "en-US") -> int:
    """Load hook config and execute the pre-push validation flow."""
    config = _load_hook_config_or_exit_zero(hook_dir)
    if config is None:
        return 0

    all_commits, branch = _collect_pre_push_commits()
    return run_check(all_commits, branch, config, TRIGGER_PUSH, locale)


def main_commit_msg(hook_dir: Path, locale: str = "en-US") -> int:
    """Load hook config and execute the commit-msg validation flow."""
    config = _load_hook_config_or_exit_zero(hook_dir)
    if config is None:
        return 0

    if len(sys.argv) < 2:
        print(translate(config.locale, "usage_commit_msg"), file=sys.stderr)
        return 1

    message = read_commit_message(Path(sys.argv[1]))
    commit = CommitInfo(hash=ZERO_SHA, message=message, author_display_name=get_author())
    return run_check([commit], get_current_branch(), config, TRIGGER_COMMIT, locale)


def run_pre_push(url: str, secret: str, locale: str = "en-US") -> int:
    """Entry point for the ``pre-push`` git hook.

    Reads the push refs from *stdin*, collects all commits to be pushed, and
    validates them against the Process Guardian endpoint.

    Args:
        url:    The web-trigger URL (include ``?repoSlug=<slug>`` for repo-scope).
        secret: The HMAC secret shown in the "Configure token" dialog.
        locale: BCP-47 locale for rule messages (default ``"en-US"``).

    Returns:
        ``0`` to allow the push, ``1`` to block it.
    """
    config = CommitCheckConfig(url=url, secret=secret)
    all_commits, branch = _collect_pre_push_commits()
    return run_check(all_commits, branch, config, TRIGGER_PUSH, locale)


def run_commit_msg(url: str, secret: str, locale: str = "en-US") -> int:
    """Entry point for the ``commit-msg`` git hook.

    Reads the commit message from the file path passed as ``sys.argv[1]``,
    then validates it against the Process Guardian endpoint.

    Args:
        url:    The web-trigger URL (include ``?repoSlug=<slug>`` for repo-scope).
        secret: The HMAC secret shown in the "Configure token" dialog.
        locale: BCP-47 locale for rule messages (default ``"en-US"``).

    Returns:
        ``0`` to allow the commit, ``1`` to block it.
    """
    if len(sys.argv) < 2:
        print(translate(locale, "usage_commit_msg"), file=sys.stderr)
        return 1

    config = CommitCheckConfig(url=url, secret=secret)
    message = read_commit_message(Path(sys.argv[1]))
    commit = CommitInfo(hash=ZERO_SHA, message=message, author_display_name=get_author())
    return run_check([commit], get_current_branch(), config, TRIGGER_COMMIT, locale)
