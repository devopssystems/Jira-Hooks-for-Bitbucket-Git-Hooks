"""ResultPrinter — formats and prints validation results to stdout/stderr."""

from __future__ import annotations
import sys
import re as _re
from typing import TYPE_CHECKING, Any, Callable, FrozenSet, cast

from .i18n import DEFAULT_LOCALE, section_label, source_label, translate
from .output_level import OutputComponent
from .printer_constants import (
    CHECK_MSG_INDENT,
    COMMIT_HASH_RE,
    CONTEXT_TO_SECTION,
    RESULT_ICON_RICH,
    RESULT_RICH_STYLE,
    RESULT_ICON,
    SECTION_ORDER,
    SEPARATOR,
    STATUS_ICON,
    STATUS_ICON_RICH,
    STATUS_RICH_STYLE,
    SYSTEM_SOURCES,
)
from .severity_filter import SeverityFilter

if TYPE_CHECKING:
    from .result import CheckResult


_CURRENT_COMMIT_PLACEHOLDER_RE = _re.compile(r"\b0{7,40}\b")

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

# ---------------------------------------------------------------------------
# Rich terminal formatting support.
# ---------------------------------------------------------------------------
_has_rich = False
_RichConsole: Any = None
_RichPadding: Any = None
_RichTable: Any = None
_RichText: Any = None
_markup_escape: Any = None
try:
    from rich.console import Console as _RichConsole
    from rich.padding import Padding as _RichPadding
    from rich.table import Table as _RichTable
    from rich.text import Text as _RichText
    from rich.markup import escape as _markup_escape
    _has_rich = True
except ImportError:
    pass


def _get_facts(d: dict[str, object], key: str) -> list[dict[str, object]]:
    val = d.get(key)
    if not isinstance(val, list):
        return []
    result: list[dict[str, object]] = []
    for item in cast(list[object], val):
        if isinstance(item, dict):
            result.append(item)  # type: ignore[arg-type]
    return result


def _get_messages(d: dict[str, object], key: str) -> list[dict[str, object]]:
    val = d.get(key)
    if not isinstance(val, list):
        return []
    result: list[dict[str, object]] = []
    for item in cast(list[object], val):
        if isinstance(item, dict):
            result.append(item)  # type: ignore[arg-type]
    return result


def _as_dict(val: object) -> dict[str, object]:
    if isinstance(val, dict):
        return cast(dict[str, object], val)
    return {}


def _as_object_list(val: object) -> list[object]:
    if isinstance(val, list):
        return cast(list[object], val)
    return []


def _fact_dedupe_key(fact: dict[str, object]) -> tuple[str, str, str, str, str, tuple[str, ...], str, str]:
    contexts = tuple(str(context) for context in _as_object_list(fact.get("contexts")))
    return (
        str(fact.get("ref") or ""),
        str(fact.get("source") or ""),
        str(fact.get("code") or ""),
        str(fact.get("group") or ""),
        str(fact.get("status") or ""),
        contexts,
        str(fact.get("ruleTitle") or ""),
        str(fact.get("message") or ""),
    )

def _primary_context(fact: dict[str, object]) -> str:
    contexts = _as_object_list(fact.get("contexts"))
    if not contexts:
        return "GLOBAL"
    return str(contexts[0]).upper()


def _section_rule_status(rule_status: str, summary_fact: dict[str, object]) -> str:
    summary_status = str(summary_fact.get("status") or "").upper()
    if summary_status == "ERROR":
        return "BLOCK"
    if summary_status in {"SUCCESS", "WARNING", "INFO", "MATCH"}:
        return "PASS"
    return rule_status


def _section_name_for_fact(fact: dict[str, object]) -> str | None:
    primary_ctx = _primary_context(fact)
    if primary_ctx not in {"COMMIT", "COMMITS", "BRANCH_SOURCE", "BRANCH_DESTINATION"}:
        return None
    return CONTEXT_TO_SECTION.get(primary_ctx, "GLOBAL")


def _is_section_summary_fact(fact: dict[str, object]) -> bool:
    return (
        str(fact.get("source", "")).upper() == "AGGREGATE"
        and str(fact.get("group", "")).upper() == "TARGET"
    )


def _is_section_detail_fact(fact: dict[str, object]) -> bool:
    return str(fact.get("group", "")).upper() not in {"MAIN", "TARGET"}


def compute_result_stats(
    check_result: CheckResult,
    *,
    is_visible: Callable[[dict[str, object]], bool],
) -> dict[str, int]:
    """Return summary counters for rule outcomes and visible fact severities."""
    blocked = passed = skipped = 0
    error_count = warning_count = info_count = success_count = 0
    for rv in check_result.rule_validations:
        rule_status = str(rv.get("ruleStatus", ""))
        if rule_status == "BLOCK":
            blocked += 1
        elif rule_status == "PASS":
            passed += 1
        elif rule_status in {"SKIP", "IGNORE"}:
            skipped += 1
        elif any(
            str(fact.get("status", "")).upper() == "SKIP"
            and str(fact.get("group", "")).upper() == "MAIN"
            for fact in _get_facts(rv, "conditionFacts")
        ):
            skipped += 1
        all_facts = _get_facts(rv, "conditionFacts") + _get_facts(rv, "checkFacts")
        for fact in all_facts:
            if not is_visible(fact):
                continue
            status = str(fact.get("status", "")).upper()
            if status == "ERROR":
                error_count += 1
            elif status == "WARNING":
                warning_count += 1
            elif status == "INFO":
                info_count += 1
            elif status in {"SUCCESS", "MATCH"}:
                success_count += 1
    return {
        "blocked": blocked,
        "passed": passed,
        "skipped": skipped,
        "total_rules": len(check_result.rule_validations),
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "success_count": success_count,
    }

class ResultPrinter:
    """Prints a :class:`~jhfb_hooks.result.CheckResult` to stdout/stderr."""

    def __init__(
        self,
        output_levels: FrozenSet[OutputComponent],
        rich_enabled: bool = True,
        severity_filter: SeverityFilter = SeverityFilter.ERROR,
        show_conditions: bool = True,
        locale: str = "en-US",
    ) -> None:
        self._output_levels = output_levels
        self._severity_filter = severity_filter
        self._show_conditions = show_conditions
        self._locale = locale.strip() or DEFAULT_LOCALE
        self._rich_active = rich_enabled and _has_rich
        self._console_out: Any = _RichConsole(file=sys.stdout, highlight=False) if self._rich_active else None
        self._console_err: Any = _RichConsole(file=sys.stderr, highlight=False) if self._rich_active else None

    def print_result(self, check_result: CheckResult, commit_count: int, elapsed: float = 0.0) -> None:
        """Print the full validation result as a structured report."""
        if self._has(OutputComponent.DISABLED):
            return
        to_stdout = not check_result.is_blocked()
        write = self._out if to_stdout else self._err

        write("")
        if self._has(OutputComponent.SUMMARY):
            self._print_header(write, check_result)
        if self._wants_any_rule_section():
            self._print_rule_sections(write, check_result)

        if self._has(OutputComponent.SUMMARY):
            self._print_system_checks(write, check_result)

        self._print_error_validations(write, check_result)

        if elapsed > 0:
            write("")
            self._print_timing_line(write, check_result, elapsed)
        write("")

    def _print_timing_line(self, write: Any, check_result: CheckResult, elapsed: float) -> None:
        stats = self._compute_stats(check_result)
        executed = stats["blocked"] + stats["passed"]
        skipped = stats["skipped"]
        executed_word = translate(self._locale, "timing_rule_singular") if executed == 1 else translate(self._locale, "timing_rule_plural")
        skipped_word = translate(self._locale, "timing_rule_singular") if skipped == 1 else translate(self._locale, "timing_rule_plural")
        line = (
            f"  {executed} {executed_word} {translate(self._locale, 'timing_validated')}. "
            f"{skipped} {skipped_word} {translate(self._locale, 'timing_skipped')} in {elapsed:.2f}s"
        )
        write(f"  [dim]{line.strip()}[/dim]" if self._rich_active else line)

    def _has(self, level: OutputComponent) -> bool:
        return level in self._output_levels

    def _wants_any_rule_section(self) -> bool:
        return any(
            self._has(level)
            for level in (
                OutputComponent.RULES_TITLE,
                OutputComponent.RULES_META,
                OutputComponent.RULE_SUMMARY,
                OutputComponent.RULES_DETAILED,
            )
        )

    def _uses_compact_rule_spacing(self) -> bool:
        return self._has(OutputComponent.RULES_TITLE)

    def print_http_error(self, status_code: int, body: object) -> None:
        """Print an HTTP error message to stderr."""
        self._err(translate(self._locale, "http_error", status_code=status_code, body=body))

    def print_connection_error(self, exc: Exception) -> None:
        """Print a network error message to stderr."""
        self._err(translate(self._locale, "connection_error", error=exc))

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def _compute_stats(self, check_result: CheckResult) -> dict[str, int]:
        return compute_result_stats(check_result, is_visible=self._is_visible)

    # ------------------------------------------------------------------
    # Section printers
    # ------------------------------------------------------------------

    def _display_message(self, message: str) -> str:
        return _CURRENT_COMMIT_PLACEHOLDER_RE.sub(translate(self._locale, "current_commit"), message)

    def _display_commit_ref(self, ref: str) -> str:
        if _CURRENT_COMMIT_PLACEHOLDER_RE.fullmatch(ref):
            return translate(self._locale, "current_commit")
        return ref[:8]

    def _rule_entry_label_width(self) -> int:
        labels = (
            translate(self._locale, "rule_error"),
            translate(self._locale, "rule_success"),
            translate(self._locale, "rule_hint"),
            translate(self._locale, "rule_summary"),
        )
        return max(len(label) for label in labels) + 4

    def _print_header(self, write: Any, check_result: CheckResult) -> None:
        title = translate(self._locale, "header_title")
        sep = f"[dim]{SEPARATOR}[/dim]" if self._rich_active else SEPARATOR
        write(f"[bold]{title}[/bold]" if self._rich_active else title)
        write(sep)
        write("")
        if check_result.is_blocked():
            result_line = translate(self._locale, "header_blocked")
            write(f"[bold red]{result_line}[/bold red]" if self._rich_active else result_line)
        else:
            result_line = translate(self._locale, "header_passed")
            write(f"[bold green]{result_line}[/bold green]" if self._rich_active else result_line)

    def _print_summary(self, write: Any, stats: dict[str, int]) -> None:
        write("")
        if self._rich_active:
            write("[bold]Validation Summary[/bold]")
            write("[dim]##################[/dim]")
        else:
            write("Validation Summary")
            write("##################")
        write("")
        total = stats["total_rules"]
        blocked = stats["blocked"]
        passed = stats["passed"]
        if blocked > 0:
            rule_word = "rule" if total == 1 else "rules"
            label = f"✗ {blocked} out of {total} validation {rule_word} failed"
            write(f"  [red]{label}[/red]" if self._rich_active else f"  {label}")
        if passed > 0:
            rule_word = "rule" if passed == 1 else "rules"
            label = f"✓ {passed} validation {rule_word} completed successfully"
            write(f"  [green]{label}[/green]" if self._rich_active else f"  {label}")
        error_count = stats["error_count"]
        warning_count = stats["warning_count"]
        info_count = stats["info_count"]
        success_count = stats["success_count"]
        if error_count > 0:
            check_word = "check" if error_count == 1 else "checks"
            label = f"✗ {error_count} {check_word} reported errors"
            write(f"  [red]{label}[/red]" if self._rich_active else f"  {label}")
        if warning_count > 0:
            check_word = "check" if warning_count == 1 else "checks"
            label = f"! {warning_count} {check_word} reported warnings"
            write(f"  [yellow]{label}[/yellow]" if self._rich_active else f"  {label}")
        if info_count > 0:
            check_word = "check was" if info_count == 1 else "checks were"
            label = f"i {info_count} informational {check_word} reported"
            write(f"  [cyan]{label}[/cyan]" if self._rich_active else f"  {label}")
        if success_count > 0:
            check_word = "check" if success_count == 1 else "checks"
            label = f"✓ {success_count} {check_word} completed successfully"
            write(f"  [green]{label}[/green]" if self._rich_active else f"  {label}")

    def _print_rule_list(self, write: Any, check_result: CheckResult) -> None:
        write("")
        write("The following validation rules were executed:")
        write("")
        if not check_result.rule_validations:
            write("  i No rules are configured for this check type.")
            return
        for rv in check_result.rule_validations:
            rule = _as_dict(rv.get("rule"))
            title = str(rule.get("title", "?"))
            status = str(rv.get("ruleStatus", ""))
            if self._rich_active:
                icon = RESULT_ICON_RICH.get(status, "")
                style = RESULT_RICH_STYLE.get(status, "")
                escaped = _markup_escape(title)
                styled = f"[{style}]{escaped}[/{style}]" if style else escaped
                write(f"  {icon} {styled}")
            else:
                icon = RESULT_ICON.get(status, "")
                write(f"  {icon} {title}")

    def _print_rules_section(self, write: Any, check_result: CheckResult) -> None:
        rules_to_show = [rv for rv in check_result.rule_validations if self._should_show_rule_detail(rv)]
        if not rules_to_show:
            return
        sep = f"[dim]{SEPARATOR}[/dim]" if self._rich_active else SEPARATOR
        write("")
        write(sep)
        write("")
        write("[bold]Validation Rules[/bold]" if self._rich_active else "Validation Rules")
        write("")
        for rv in rules_to_show:
            write(sep)
            write("")
            self._print_rule_detail_block(write, rv)
            write("")

    def _print_rule_detail_block(self, write: Any, rv: dict[str, object]) -> None:
        rule = _as_dict(rv.get("rule"))
        title = str(rule.get("title", "?"))
        status = str(rv.get("ruleStatus", ""))
        if self._rich_active:
            icon = RESULT_ICON_RICH.get(status, "")
            style = RESULT_RICH_STYLE.get(status, "")
            escaped_title = _markup_escape(title)
            bold_style = f"bold {style}" if style else "bold"
            write(f"{icon} [bold]Rule:[/bold] [{bold_style}]{escaped_title}[/{bold_style}]")
        else:
            icon = RESULT_ICON.get(status, "")
            write(f"{icon} Rule: {title}")
        write("")
        if status == "BLOCK":
            error = self._display_message(str(rule.get("error") or ""))
            hint = self._display_message(str(rule.get("hint") or ""))
            if error:
                label = translate(self._locale, "validation_result")
                write(f"  [bold]{label}[/bold] {_markup_escape(error)}" if self._rich_active else f"  {label} {error}")
            if hint and hint != error:
                label = translate(self._locale, "recommendation")
                write(f"  [bold]{label}[/bold] {_markup_escape(hint)}" if self._rich_active else f"  {label} {hint}")
        condition_facts = _get_facts(rv, "conditionFacts")
        check_facts = _get_facts(rv, "checkFacts")

        if self._show_conditions:
            self._print_conditions_section(write, condition_facts)

        all_facts = check_facts
        # group=TARGET + GLOBAL context facts are always shown regardless of output level or severity filter
        always_shown: list[dict[str, object]] = [
            f for f in all_facts
            if str(f.get("group", "")).upper() == "TARGET"
            and any(str(c).upper() == "GLOBAL" for c in cast(list[object], f.get("contexts") or []))
        ]
        always_shown_ids: set[int] = {id(f) for f in always_shown}
        visible = [f for f in all_facts if self._is_visible(f) and id(f) not in always_shown_ids]
        if not visible and not always_shown:
            return
        # Separate TARGET-source facts: global ones at top, per-commit ones inside commit blocks
        target_global: list[dict[str, object]] = list(always_shown)
        target_by_ref: dict[str, dict[str, object]] = {}
        check_facts: list[dict[str, object]] = []
        for f in visible:
            if str(f.get("source", "")).upper() == "TARGET":
                ref = str(f.get("ref") or "")
                if ref and COMMIT_HASH_RE.match(ref):
                    target_by_ref[ref] = f
                else:
                    target_global.append(f)
            else:
                check_facts.append(f)
        self._write_target_header(write)
        if target_global:
            write("")
            self._write_target_facts(write, target_global)
        if not check_facts:
            return
        self._print_check_facts_by_section(write, check_facts, target_by_ref)

    def _write_target_header(self, write: Any) -> None:
        write("")
        if self._rich_active:
            write(f"  [bold]{translate(self._locale, 'validated_target')}:[/bold]")
            write("  [dim]-----------------------[/dim]")
        else:
            write(f"  {translate(self._locale, 'validated_target')}:")
            write("  -----------------------")

    def _write_target_facts(self, write: Any, facts: list[dict[str, object]]) -> None:
        for f in facts:
            msg = self._display_message(str(f.get("message", "")))
            t_status = str(f.get("status", ""))
            if self._rich_active:
                t_icon = STATUS_ICON_RICH.get(t_status, " ")
                write(f"    {t_icon} [dim]{_markup_escape(msg)}[/dim]")
            else:
                t_icon = STATUS_ICON.get(t_status, " ")
                write(f"    {t_icon} {msg}")

    def _print_check_facts_by_section(
        self,
        write: Any,
        check_facts: list[dict[str, object]],
        target_by_ref: dict[str, dict[str, object]],
    ) -> None:
        section_facts: dict[str, list[dict[str, object]]] = {}
        for f in check_facts:
            ctx_val = f.get("contexts")
            contexts: list[object] = cast(list[object], ctx_val) if isinstance(ctx_val, list) else []
            primary_ctx = str(contexts[0]).upper() if contexts else "GLOBAL"
            section = CONTEXT_TO_SECTION.get(primary_ctx, "GLOBAL")
            if section not in section_facts:
                section_facts[section] = []
            section_facts[section].append(f)
        for section in SECTION_ORDER:
            if section not in section_facts:
                continue
            facts = section_facts[section]
            label = section_label(self._locale, section)
            write("")
            if self._rich_active:
                write(f"    [bold]{label}:[/bold]")
                write("    [dim]---------------[/dim]")
            else:
                write(f"    {label}:")
                write("    ---------------")
            if section == "COMMITS":
                self._print_commits_section(write, facts, target_by_ref)
            else:
                aggregate_facts, other_facts = self._split_aggregate_facts(facts)
                section_msg_indent = "    " if section == "BRANCH" else CHECK_MSG_INDENT
                if aggregate_facts:
                    self._print_fact_messages(write, aggregate_facts, msg_indent="    ")
                if other_facts:
                    if aggregate_facts:
                        write("")
                    self._print_source_groups(write, other_facts, cat_indent="    ", msg_indent=section_msg_indent)

    def _print_commits_section(
        self,
        write: Any,
        facts: list[dict[str, object]],
        target_by_ref: dict[str, dict[str, object]],
    ) -> None:
        """Render commit facts grouped by hash, each with an optional TARGET description."""
        ref_order: list[str] = []
        ref_map: dict[str, list[dict[str, object]]] = {}
        for f in facts:
            ref = str(f.get("ref") or "")
            if ref not in ref_map:
                ref_map[ref] = []
                ref_order.append(ref)
            ref_map[ref].append(f)
        for ref in ref_order:
            if ref and COMMIT_HASH_RE.match(ref):
                write("")
                display_ref = self._display_commit_ref(ref)
                write(f"    [bold]{_markup_escape(display_ref)}[/bold]" if self._rich_active else f"    {display_ref}")
                target_f = target_by_ref.get(ref)
                if target_f:
                    target_msg = self._display_message(str(target_f.get("message", "")))
                    target_status = str(target_f.get("status", ""))
                    if target_msg:
                        write("")
                        if self._rich_active:
                            t_icon = STATUS_ICON_RICH.get(target_status, " ")
                            write(f"      {t_icon} [dim]{_markup_escape(target_msg)}[/dim]")
                        else:
                            t_icon = STATUS_ICON.get(target_status, " ")
                            write(f"      {t_icon} {target_msg}")
                write("")
                self._print_source_groups(write, ref_map[ref], cat_indent="        ", msg_indent="        ")
                continue

            aggregate_facts = [f for f in ref_map[ref] if str(f.get("source", "")).upper() == "AGGREGATE"]
            other_facts = [f for f in ref_map[ref] if str(f.get("source", "")).upper() != "AGGREGATE"]
            if aggregate_facts:
                self._print_fact_messages(write, aggregate_facts, msg_indent="    ")
            if other_facts:
                if aggregate_facts:
                    write("")
                self._print_source_groups(write, other_facts, cat_indent="        ", msg_indent="        ")

    def _print_source_groups(
        self,
        write: Any,
        facts: list[dict[str, object]],
        cat_indent: str,
        msg_indent: str,
    ) -> None:
        """Render facts grouped by source with a human-readable check heading."""
        source_order: list[str] = []
        source_map: dict[str, list[dict[str, object]]] = {}
        for f in facts:
            if str(f.get("group", "")).upper() == "MAIN":
                continue
            source = str(f.get("source", "UNKNOWN"))
            if source not in source_map:
                source_map[source] = []
                source_order.append(source)
            source_map[source].append(f)
        for index, source in enumerate(source_order):
            if index > 0:
                write("")
            label = source_label(self._locale, source)
            if self._rich_active:
                write(f"{cat_indent}{_markup_escape(label)}")
            else:
                write(f"{cat_indent}{label}")
            self._print_fact_messages(write, source_map[source], msg_indent=msg_indent)

    def _print_fact_messages(self, write: Any, facts: list[dict[str, object]], msg_indent: str) -> None:
        for f in facts:
            f_status = str(f.get("status", ""))
            message = self._display_message(str(f.get("message", "")))
            if self._rich_active:
                write(self._build_rich_fact_renderable(msg_indent, f_status, message))
            else:
                f_icon = STATUS_ICON.get(f_status, " ")
                write(f"{msg_indent}{f_icon} {message}")

    def _print_conditions_section(self, write: Any, facts: list[dict[str, object]]) -> None:
        visible = [f for f in facts if self._is_visible(f)]
        if not visible:
            return

        write("")
        if self._rich_active:
            write(f"  [bold]{translate(self._locale, 'conditions')}:[/bold]")
            write("  [dim]---------------[/dim]")
        else:
            write(f"  {translate(self._locale, 'conditions')}:")
            write("  ---------------")

        aggregate_facts, other_facts = self._split_aggregate_facts(visible)
        if aggregate_facts:
            self._print_fact_messages(write, aggregate_facts, msg_indent="  ")
        if other_facts:
            if aggregate_facts:
                write("")
            self._print_source_groups(write, other_facts, cat_indent="    ", msg_indent="    ")

    def _split_aggregate_facts(
        self,
        facts: list[dict[str, object]],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        aggregate_facts: list[dict[str, object]] = []
        other_facts: list[dict[str, object]] = []
        for f in facts:
            if str(f.get("source", "")).upper() == "AGGREGATE":
                aggregate_facts.append(f)
            else:
                other_facts.append(f)
        return aggregate_facts, other_facts

    def _build_rich_fact_renderable(self, msg_indent: str, status: str, message: str) -> Any:
        icon = STATUS_ICON.get(status, " ")
        style = STATUS_RICH_STYLE.get(status, "dim")
        grid = _RichTable.grid(padding=(0, 1), expand=True)
        grid.add_column(width=1, no_wrap=True)
        grid.add_column(ratio=1, overflow="fold")
        grid.add_row(
            _RichText(icon, style=style),
            _RichText(message, style="dim"),
        )
        return _RichPadding(grid, (0, 0, 0, len(msg_indent)))

    def _build_rich_message_renderable(self, msg_indent: str, message: str, style: str = "dim") -> Any:
        grid = _RichTable.grid(expand=True)
        grid.add_column(ratio=1, overflow="fold")
        grid.add_row(_RichText(message, style=style))
        return _RichPadding(grid, (0, 0, 0, len(msg_indent)))

    def _build_rich_labeled_message_renderable(
        self,
        msg_indent: str,
        label: str,
        message: str,
        style: str = "dim",
    ) -> Any:
        grid = _RichTable.grid(expand=True)
        grid.add_column(width=self._rule_entry_label_width(), no_wrap=True)
        grid.add_column(ratio=1, overflow="fold")
        grid.add_row(_RichText(label, style=style), _RichText(message, style=style))
        return _RichPadding(grid, (0, 0, 0, len(msg_indent)))

    def _print_rule_sections(self, write: Any, check_result: CheckResult) -> None:
        show_entries = self._has(OutputComponent.RULES_TITLE) or self._has(OutputComponent.RULES_META) or self._has(OutputComponent.RULE_SUMMARY)
        show_details = self._has(OutputComponent.RULES_DETAILED)
        if show_details and self._show_conditions:
            condition_facts: list[dict[str, object]] = []
            for rv in check_result.rule_validations:
                condition_facts.extend(_get_facts(rv, "conditionFacts"))
            self._print_conditions_section(write, condition_facts)

        section_entries = self._collect_rule_section_entries(check_result)
        section_details = self._collect_rules_detailed_section_facts(check_result) if show_details else {}
        if not section_entries and not section_details:
            return

        for section in SECTION_ORDER:
            entries = section_entries.get(section, []) if show_entries else []
            details = self._dedupe_facts(section_details.get(section, []))
            if not entries and not details:
                continue
            label = section_label(self._locale, section)
            write("")
            if self._rich_active:
                write(f"  [bold]{label}:[/bold]")
                write("  [dim]---------------[/dim]")
            else:
                write(f"  {label}:")
                write("  ---------------")

            compact_rule_spacing = self._uses_compact_rule_spacing()
            for index, entry in enumerate(entries):
                if index > 0 and not compact_rule_spacing:
                    write("")
                self._print_rule_section_entry(write, entry)

            if show_details and details:
                if entries:
                    write("")
                if section == "COMMITS":
                    self._print_rules_detailed_commit_facts(write, details)
                else:
                    self._print_rules_detailed_section_facts(write, details, msg_indent="  ")

    def _print_rules_detailed_commit_facts(self, write: Any, facts: list[dict[str, object]]) -> None:
        ref_order: list[str] = []
        ref_map: dict[str, list[dict[str, object]]] = {}
        for f in facts:
            ref = str(f.get("ref") or "")
            if ref not in ref_map:
                ref_map[ref] = []
                ref_order.append(ref)
            ref_map[ref].append(f)
        for index, ref in enumerate(ref_order):
            if index > 0:
                write("")
            if ref and COMMIT_HASH_RE.match(ref):
                display_ref = self._display_commit_ref(ref)
                if self._rich_active:
                    write(f"  [bold]{_markup_escape(display_ref)}[/bold]")
                else:
                    write(f"  {display_ref}")
                self._print_fact_messages(write, ref_map[ref], msg_indent="    ")
            else:
                self._print_fact_messages(write, ref_map[ref], msg_indent="  ")

    def _print_rules_detailed_section_facts(self, write: Any, facts: list[dict[str, object]], msg_indent: str) -> None:
        self._print_fact_messages(write, facts, msg_indent=msg_indent)

    def _dedupe_facts(self, facts: list[dict[str, object]]) -> list[dict[str, object]]:
        deduped: list[dict[str, object]] = []
        seen: set[tuple[str, str, str, str, str, tuple[str, ...], str, str]] = set()
        for fact in facts:
            key = _fact_dedupe_key(fact)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(fact)
        return deduped

    def _iter_visible_section_facts(self, rv: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
        section_facts: list[tuple[str, dict[str, object]]] = []
        for fact in _get_facts(rv, "checkFacts"):
            section = _section_name_for_fact(fact)
            if section is None or not self._is_visible(fact):
                continue
            section_facts.append((section, fact))
        return section_facts

    def _collect_rules_detailed_section_facts(self, check_result: CheckResult) -> dict[str, list[dict[str, object]]]:
        section_facts: dict[str, list[dict[str, object]]] = {}
        for rv in check_result.rule_validations:
            for section, fact in self._iter_visible_section_facts(rv):
                if not _is_section_detail_fact(fact):
                    continue
                section_facts.setdefault(section, []).append(fact)
        return section_facts

    def _collect_rule_section_entries(self, check_result: CheckResult) -> dict[str, list[dict[str, object]]]:
        sections: dict[str, list[dict[str, object]]] = {}
        for rv in check_result.rule_validations:
            rule = _as_dict(rv.get("rule"))
            rule_title = str(rule.get("title") or "?").strip()
            rule_status = str(rv.get("ruleStatus") or "")
            summary_by_section: dict[str, dict[str, object]] = {}
            rule_sections: set[str] = set()
            for section, fact in self._iter_visible_section_facts(rv):
                if _is_section_summary_fact(fact):
                    summary_by_section[section] = fact
                    rule_sections.add(section)
                elif _is_section_detail_fact(fact):
                    rule_sections.add(section)

            for section in rule_sections:
                sections.setdefault(section, []).append({
                    "ruleTitle": rule_title,
                    "ruleStatus": _section_rule_status(rule_status, summary_by_section.get(section, {})),
                    "error": str(rule.get("error") or ""),
                    "hint": str(rule.get("hint") or ""),
                    "success": str(rule.get("success") or ""),
                    "summaryMessage": str(summary_by_section.get(section, {}).get("message") or ""),
                })
        return sections

    def _print_rule_section_entry(self, write: Any, entry: dict[str, object]) -> None:
        status = str(entry.get("ruleStatus") or "")
        rule_title = str(entry.get("ruleTitle") or "")
        error = self._display_message(str(entry.get("error") or ""))
        hint = self._display_message(str(entry.get("hint") or ""))
        success = self._display_message(str(entry.get("success") or ""))
        summary_message = self._display_message(str(entry.get("summaryMessage") or ""))
        show_title = self._has(OutputComponent.RULES_TITLE)
        if show_title:
            if self._rich_active:
                icon = RESULT_ICON_RICH.get(status, STATUS_ICON_RICH.get(status, ""))
                write(f"  {icon} [bold]Rule:[/bold] [white]{_markup_escape(rule_title)}[/white]")
            else:
                icon = RESULT_ICON.get(status, STATUS_ICON.get(status, " "))
                write(f"  {icon} Rule: {rule_title}")

        if self._has(OutputComponent.RULES_META) and status == "BLOCK" and error:
            self._print_rule_entry_message(write, "    ", translate(self._locale, "rule_error"), error)
        elif self._has(OutputComponent.RULES_META) and status == "PASS" and success:
            self._print_rule_entry_message(write, "    ", translate(self._locale, "rule_success"), success)

        if self._has(OutputComponent.RULES_META) and status == "BLOCK" and hint and hint != error:
            self._print_rule_entry_message(write, "    ", translate(self._locale, "rule_hint"), hint)

        if self._has(OutputComponent.RULE_SUMMARY) and summary_message:
            self._print_rule_entry_message(write, "    ", translate(self._locale, "rule_summary"), summary_message)

    def _print_rule_entry_message(self, write: Any, msg_indent: str, label: str, message: str) -> None:
        if self._rich_active:
            if label:
                write(self._build_rich_labeled_message_renderable(msg_indent, label, message, style="dim"))
            else:
                write(self._build_rich_message_renderable(msg_indent, message, style="dim"))
        else:
            if label:
                write(f"{msg_indent}{label.ljust(self._rule_entry_label_width())} {message}")
            else:
                write(f"{msg_indent}{message}")

    def _print_rich_rule_prefixed_fact(self, write: Any, fact: dict[str, object], msg_indent: str, rule_title: str) -> None:
        status = str(fact.get("status", ""))
        message = self._display_message(str(fact.get("message") or ""))
        icon = STATUS_ICON.get(status, " ")
        style = STATUS_RICH_STYLE.get(status, "dim")
        title_grid = _RichTable.grid(padding=(0, 1), expand=True)
        title_grid.add_column(width=1, no_wrap=True)
        title_grid.add_column(ratio=1, overflow="fold")
        title_grid.add_row(_RichText(icon, style=style), _RichText(rule_title, style="white"))
        write(_RichPadding(title_grid, (0, 0, 0, len(msg_indent))))

        if message:
            write(self._build_rich_message_renderable(f"{msg_indent}  ", message, style="dim"))

    def _print_rule_prefixed_facts(self, write: Any, facts: list[dict[str, object]], msg_indent: str) -> None:
        for fact in facts:
            rule_title = str(fact.get("ruleTitle") or "")
            if self._rich_active and rule_title:
                self._print_rich_rule_prefixed_fact(write, fact, msg_indent=msg_indent, rule_title=rule_title)
            else:
                message = self._display_message(str(fact.get("message") or ""))
                status = str(fact.get("status", ""))
                icon = STATUS_ICON.get(status, " ")
                write(f"{msg_indent}{icon} {rule_title}")
                if message:
                    write(f"{msg_indent}  {message}")

    def _print_system_checks(self, write: Any, check_result: CheckResult) -> None:
        """Print deduplicated system-level facts (license, connection) from all rules."""
        seen: set[tuple[str, str, str]] = set()
        system_facts: list[dict[str, object]] = []
        for rv in check_result.rule_validations:
            all_facts = _get_facts(rv, "conditionFacts") + _get_facts(rv, "checkFacts")
            for f in all_facts:
                source = str(f.get("source", "")).upper()
                if source not in SYSTEM_SOURCES:
                    continue
                status = str(f.get("status", ""))
                message = self._display_message(str(f.get("message", "")))
                key = (source, status, message)
                if key not in seen:
                    seen.add(key)
                    system_facts.append(f)
        if not system_facts:
            return
        write("")
        for f in system_facts:
            f_status = str(f.get("status", ""))
            message = self._display_message(str(f.get("message", "")))
            if self._rich_active:
                f_icon = STATUS_ICON_RICH.get(f_status, " ")
                write(f"  {f_icon} [dim]{_markup_escape(message)}[/dim]")
            else:
                f_icon = STATUS_ICON.get(f_status, " ")
                write(f"  {f_icon} {message}")

    def _print_error_validations(self, write: Any, check_result: CheckResult) -> None:
        """Print collection-level validation errors returned by the endpoint."""
        if not check_result.error_validations:
            return

        lines: list[tuple[str, str]] = []
        for validation in check_result.error_validations:
            for key, status in (
                ("errorMessages", "ERROR"),
                ("warningMessages", "WARNING"),
                ("successMessages", "SUCCESS"),
                ("detailMessages", "INFO"),
            ):
                if not self._severity_filter.allows(status):
                    continue
                for msg in _get_messages(validation, key):
                    text = self._display_message(str(msg.get("text") or ""))
                    if text:
                        lines.append((status, text))

        if not lines:
            lines.append(("ERROR", translate(self._locale, "validation_failed_without_details")))

        write("")
        title = translate(self._locale, "validation_errors")
        write(f"[bold]{title}[/bold]" if self._rich_active else title)
        write("[dim]#################[/dim]" if self._rich_active else "#################")
        write("")
        for status, text in lines:
            if self._rich_active:
                icon = STATUS_ICON_RICH.get(status, " ")
                write(f"  {icon} [dim]{_markup_escape(text)}[/dim]")
            else:
                icon = STATUS_ICON.get(status, " ")
                write(f"  {icon} {text}")

    def _should_show_rule_detail(self, rv: dict[str, object]) -> bool:
        status = str(rv.get("ruleStatus", ""))
        return status == "BLOCK"

    def _is_visible(self, msg: dict[str, object]) -> bool:
        status = str(msg.get("status", ""))
        return self._severity_filter.allows(status)

    def _write(self, text: Any, *, to_stdout: bool) -> None:
        if self._rich_active:
            console = self._console_out if to_stdout else self._console_err
            console.print(text)
        else:
            print(text, file=sys.stdout if to_stdout else sys.stderr)

    def _out(self, text: str) -> None:
        self._write(text, to_stdout=True)

    def _err(self, text: str) -> None:
        self._write(text, to_stdout=False)
