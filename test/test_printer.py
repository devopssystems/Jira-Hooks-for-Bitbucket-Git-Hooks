"""Unit tests for jhfb_hooks.printer and related modules."""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Make the package importable when running from local-hooks/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jhfb_hooks.output_level import OutputComponent
from jhfb_hooks.payload import TRIGGER_COMMIT, TRIGGER_PUSH, build_payload
from jhfb_hooks.printer_constants import SYSTEM_SOURCES
from jhfb_hooks.runner import run_check
from jhfb_hooks.config import CommitCheckConfig, ConfigInvalidValueError, ConfigMissingKeyError, ConfigNotFoundError, load_config
from jhfb_hooks.result_printer import ResultPrinter, compute_result_stats
from jhfb_hooks.severity_filter import SEVERITY_LEVEL, SeverityFilter
from jhfb_hooks.result import CheckResult, parse_response
from jhfb_hooks.git import CommitInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OUTPUT_DISABLED = frozenset({OutputComponent.DISABLED})
OUTPUT_SUMMARY = frozenset({OutputComponent.SUMMARY})
OUTPUT_RULES_ONLY = frozenset({
    OutputComponent.SUMMARY,
    OutputComponent.RULES_TITLE,
    OutputComponent.RULES_META,
})
OUTPUT_RULES_DETAILED = frozenset({
    OutputComponent.SUMMARY,
    OutputComponent.RULES_TITLE,
    OutputComponent.RULES_META,
    OutputComponent.RULE_SUMMARY,
    OutputComponent.RULES_DETAILED,
})

def _make_fact(
    status: str,
    message: str = "msg",
    source: str = "ISSUE_KEY",
    contexts: list[str] | None = None,
    ref: str = "",
    group: str = "DETAIL",
) -> dict[str, object]:
    return {
        "status": status,
        "message": message,
        "source": source,
        "contexts": contexts or ["COMMIT"],
        "ref": ref,
        "group": group,
        "category": ["CONVENTION"],
        "params": {},
    }


def _make_rule_validation(
    rule_status: str,
    title: str = "Test Rule",
    error: str = "",
    hint: str = "",
    success: str = "",
    check_facts: list[dict[str, object]] | None = None,
    condition_facts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "ruleStatus": rule_status,
        "rule": {
            "title": title,
            "error": error,
            "hint": hint,
            "success": success,
        },
        "checkFacts": check_facts or [],
        "conditionFacts": condition_facts or [],
    }


def _make_result(
    blocked: bool,
    rule_validations: list[dict[str, object]] | None = None,
) -> CheckResult:
    result_str = "BLOCK" if blocked else "PASS"
    return CheckResult(result=result_str, rule_validations=rule_validations or [])


def _capture(
    printer: ResultPrinter,
    check_result: CheckResult,
) -> tuple[str, str]:
    """Return (stdout, stderr) captured while printing."""
    out = io.StringIO()
    err = io.StringIO()
    with patch.object(sys, "stdout", out), patch.object(sys, "stderr", err):
        printer.print_result(check_result, commit_count=1)
    return out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------

class TestPayload(unittest.TestCase):
    def test_push_payload_matches_local_check_endpoint_shape(self) -> None:
        payload = build_payload(
            [CommitInfo(hash="abc123", message="ABC-1 work", author_display_name="Alice")],
            branch="feature/ABC-1",
            trigger_type=TRIGGER_PUSH,
            locale="de-DE",
        )

        data = json.loads(payload)

        self.assertEqual(data["branchName"], "feature/ABC-1")
        self.assertEqual(data["locale"], "de-DE")
        self.assertEqual(data["triggerType"], "PUSH")
        self.assertEqual(data["commits"][0]["hash"], "abc123")
        self.assertNotIn("commit", data)

    def test_commit_payload_uses_commits_array_even_without_branch(self) -> None:
        payload = build_payload(
            [CommitInfo(hash="0" * 40, message="ABC-1 work", author_display_name="Alice")],
            branch=None,
            trigger_type=TRIGGER_COMMIT,
        )

        data = json.loads(payload)

        self.assertEqual(data["branchName"], "")
        self.assertEqual(data["triggerType"], "COMMIT")
        self.assertEqual(len(data["commits"]), 1)
        self.assertNotIn("commit", data)

    def test_payload_allows_branch_only_validation(self) -> None:
        payload = build_payload(
            [],
            branch="feature/ABC-1",
            trigger_type=TRIGGER_COMMIT,
        )

        data = json.loads(payload)

        self.assertEqual(data["branchName"], "feature/ABC-1")
        self.assertEqual(data["triggerType"], "COMMIT")
        self.assertEqual(data["commits"], [])


class TestRunner(unittest.TestCase):
    @patch("jhfb_hooks.runner.send_check")
    @patch("jhfb_hooks.runner.ResultPrinter")
    def test_run_check_sends_branch_only_payload(self, printer_cls: object, send_check: object) -> None:
        send_check.return_value = (200, {"result": "PASS", "ruleValidations": [], "errorValidations": []})
        config = CommitCheckConfig(url="https://example.invalid/check", secret="secret")

        exit_code = run_check([], "feature/ABC-1", config, TRIGGER_COMMIT)

        self.assertEqual(exit_code, 0)
        self.assertTrue(send_check.called)
        payload = send_check.call_args.args[1]
        self.assertIn('"branchName":"feature/ABC-1"', payload)
        self.assertIn('"commits":[]', payload)
        printer_cls.return_value.print_result.assert_called_once()

    @patch("jhfb_hooks.runner.send_check")
    @patch("jhfb_hooks.runner.ResultPrinter")
    def test_run_check_sends_empty_payload_and_accepts_ignore(self, printer_cls: object, send_check: object) -> None:
        send_check.return_value = (200, {"result": "IGNORE", "ruleValidations": [], "errorValidations": []})
        config = CommitCheckConfig(url="https://example.invalid/check", secret="secret")

        exit_code = run_check([], None, config, TRIGGER_PUSH)

        self.assertEqual(exit_code, 0)
        payload = send_check.call_args.args[1]
        self.assertIn('"branchName":""', payload)
        self.assertIn('"commits":[]', payload)
        printer_cls.return_value.print_result.assert_called_once()


# ---------------------------------------------------------------------------
# SeverityFilter
# ---------------------------------------------------------------------------

class TestSeverityFilter(unittest.TestCase):
    def test_error_allows_only_errors(self) -> None:
        f = SeverityFilter.ERROR
        self.assertTrue(f.allows("ERROR"))
        self.assertFalse(f.allows("WARNING"))
        self.assertFalse(f.allows("INFO"))
        self.assertFalse(f.allows("SUCCESS"))
        self.assertFalse(f.allows("MATCH"))

    def test_warning_allows_error_and_warning(self) -> None:
        f = SeverityFilter.WARNING
        self.assertTrue(f.allows("ERROR"))
        self.assertTrue(f.allows("WARNING"))
        self.assertTrue(f.allows("NOT_MATCH"))
        self.assertFalse(f.allows("INFO"))
        self.assertFalse(f.allows("SUCCESS"))

    def test_info_allows_up_to_info(self) -> None:
        f = SeverityFilter.INFO
        self.assertTrue(f.allows("ERROR"))
        self.assertTrue(f.allows("WARNING"))
        self.assertTrue(f.allows("INFO"))
        self.assertFalse(f.allows("SUCCESS"))
        self.assertFalse(f.allows("MATCH"))

    def test_success_allows_all(self) -> None:
        f = SeverityFilter.SUCCESS
        for status in ("ERROR", "WARNING", "INFO", "SUCCESS", "MATCH", "NOT_MATCH"):
            self.assertTrue(f.allows(status), status)

    def test_unknown_status_defaults_to_info_level(self) -> None:
        # Unknown maps to severity 3 (INFO), so SUCCESS filter allows it, ERROR does not
        self.assertTrue(SeverityFilter.SUCCESS.allows("UNKNOWN_STATUS"))
        self.assertFalse(SeverityFilter.ERROR.allows("UNKNOWN_STATUS"))

    def test_case_insensitive(self) -> None:
        self.assertTrue(SeverityFilter.ERROR.allows("error"))
        self.assertFalse(SeverityFilter.ERROR.allows("success"))


# ---------------------------------------------------------------------------
# SeverityLevel mapping
# ---------------------------------------------------------------------------

class TestSeverityLevelMapping(unittest.TestCase):
    def test_error_is_lowest(self) -> None:
        self.assertEqual(SEVERITY_LEVEL["ERROR"], 1)

    def test_not_match_same_as_warning(self) -> None:
        self.assertEqual(SEVERITY_LEVEL["NOT_MATCH"], SEVERITY_LEVEL["WARNING"])

    def test_match_same_as_success(self) -> None:
        self.assertEqual(SEVERITY_LEVEL["MATCH"], SEVERITY_LEVEL["SUCCESS"])


# ---------------------------------------------------------------------------
# SystemSources constant
# ---------------------------------------------------------------------------

class TestSystemSources(unittest.TestCase):
    def test_contains_expected_sources(self) -> None:
        self.assertIn("JIRA_CONNECTION", SYSTEM_SOURCES)
        self.assertIn("LICENSE", SYSTEM_SOURCES)

    def test_does_not_contain_issue_key(self) -> None:
        self.assertNotIn("ISSUE_KEY", SYSTEM_SOURCES)


# ---------------------------------------------------------------------------
# ResultPrinter — DISABLED
# ---------------------------------------------------------------------------

class TestPrinterDisabled(unittest.TestCase):
    def setUp(self) -> None:
        self.printer = ResultPrinter(
            output_levels=OUTPUT_DISABLED, rich_enabled=False
        )

    def test_produces_no_output_blocked(self) -> None:
        result = _make_result(blocked=True)
        out, err = _capture(self.printer, result)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

    def test_produces_no_output_passing(self) -> None:
        result = _make_result(blocked=False)
        out, err = _capture(self.printer, result)
        self.assertEqual(out, "")
        self.assertEqual(err, "")


# ---------------------------------------------------------------------------
# ResultPrinter — output routing (stdout vs stderr)
# ---------------------------------------------------------------------------

class TestPrinterOutputRouting(unittest.TestCase):
    def _printer(self, levels: frozenset[OutputComponent]) -> ResultPrinter:
        return ResultPrinter(output_levels=levels, rich_enabled=False, severity_filter=SeverityFilter.SUCCESS)

    def test_blocked_goes_to_stderr(self) -> None:
        result = _make_result(blocked=True)
        out, err = _capture(self._printer(OUTPUT_SUMMARY), result)
        self.assertIn("errors", err)
        self.assertEqual(out.strip(), "")

    def test_passing_goes_to_stdout(self) -> None:
        result = _make_result(blocked=False)
        out, err = _capture(self._printer(OUTPUT_SUMMARY), result)
        self.assertIn("successfully", out)
        self.assertEqual(err.strip(), "")


# ---------------------------------------------------------------------------
# ResultPrinter — SUMMARY
# ---------------------------------------------------------------------------

class TestPrinterSmall(unittest.TestCase):
    def _printer(self) -> ResultPrinter:
        return ResultPrinter(output_levels=OUTPUT_SUMMARY, rich_enabled=False)

    def test_header_present_when_blocked(self) -> None:
        result = _make_result(blocked=True)
        _, err = _capture(self._printer(), result)
        self.assertIn("Jira Hooks for Bitbucket Validation Report", err)
        self.assertIn("errors", err)

    def test_header_present_when_passing(self) -> None:
        result = _make_result(blocked=False)
        out, _ = _capture(self._printer(), result)
        self.assertIn("Jira Hooks for Bitbucket Validation Report", out)
        self.assertIn("successfully", out)

    def test_rule_details_not_present(self) -> None:
        rv = _make_rule_validation("BLOCK", title="My Rule", error="Bad commit")
        result = _make_result(blocked=True, rule_validations=[rv])
        _, err = _capture(self._printer(), result)
        self.assertNotIn("My Rule", err)
        self.assertNotIn("Bad commit", err)

    def test_leading_and_trailing_blank_lines(self) -> None:
        result = _make_result(blocked=False)
        out, _ = _capture(self._printer(), result)
        self.assertTrue(out.startswith("\n"))
        self.assertTrue(out.endswith("\n\n"))

    def test_header_is_localized_for_german_locale(self) -> None:
        result = _make_result(blocked=True)
        printer = ResultPrinter(output_levels=OUTPUT_SUMMARY, rich_enabled=False, locale="de_de")
        _, err = _capture(printer, result)
        self.assertIn("Jira Hooks for Bitbucket Validierungsbericht", err)
        self.assertIn("Die Validierung wurde mit Fehlern abgeschlossen.", err)


class TestPrinterRuleSummarySections(unittest.TestCase):
    def _printer(self) -> ResultPrinter:
        return ResultPrinter(
            output_levels=frozenset({OutputComponent.RULE_SUMMARY}),
            rich_enabled=False,
            severity_filter=SeverityFilter.SUCCESS,
        )

    def test_section_status_uses_target_summary_not_overall_rule_status(self) -> None:
        branch_target_fact = _make_fact(
            "SUCCESS",
            message="Branch validation passed.",
            source="AGGREGATE",
            contexts=["BRANCH_SOURCE"],
            group="TARGET",
        )
        commit_target_fact = _make_fact(
            "ERROR",
            message="Commit validation failed.",
            source="AGGREGATE",
            contexts=["COMMIT"],
            group="TARGET",
        )
        rv = _make_rule_validation(
            "BLOCK",
            title="Issue status",
            error="Issue status failed",
            check_facts=[branch_target_fact, commit_target_fact],
        )
        result = _make_result(blocked=True, rule_validations=[rv])

        _, err = _capture(self._printer(), result)

        self.assertIn("  Branch:\n  ---------------\n    Summary:     Branch validation passed.", err)
        self.assertIn("  Commits:\n  ---------------\n    Summary:     Commit validation failed.", err)

    def test_branch_section_does_not_pick_up_commit_only_facts(self) -> None:
        commit_target_fact = _make_fact(
            "ERROR",
            message="Commit validation failed.",
            source="AGGREGATE",
            contexts=["COMMIT"],
            group="TARGET",
        )
        commit_detail_fact = _make_fact(
            "ERROR",
            message="Commit detail failed.",
            source="JQL",
            contexts=["COMMIT"],
            ref="0000000000",
            group="DETAIL",
        )
        rv = _make_rule_validation(
            "BLOCK",
            title="Issue status",
            error="Issue status failed",
            check_facts=[commit_target_fact, commit_detail_fact],
        )
        result = _make_result(blocked=True, rule_validations=[rv])

        _, err = _capture(self._printer(), result)

        self.assertNotIn("  Branch:\n", err)
        self.assertIn("  Commits:\n  ---------------\n    Summary:     Commit validation failed.", err)

    def test_rule_title_flag_is_independent_from_summary(self) -> None:
        branch_target_fact = _make_fact(
            "SUCCESS",
            message="Branch validation passed.",
            source="AGGREGATE",
            contexts=["BRANCH_SOURCE"],
            group="TARGET",
        )
        rv = _make_rule_validation(
            "PASS",
            title="Issue status",
            success="Rule passed",
            check_facts=[branch_target_fact],
        )
        result = _make_result(blocked=False, rule_validations=[rv])
        printer = ResultPrinter(
            output_levels=frozenset({OutputComponent.RULE_SUMMARY}),
            rich_enabled=False,
            severity_filter=SeverityFilter.SUCCESS,
        )

        out, _ = _capture(printer, result)

        self.assertIn("  Branch:\n  ---------------", out)
        self.assertIn("    Summary:     Branch validation passed.", out)
        self.assertNotIn("Issue status", out)

    def test_rule_meta_flag_is_independent_from_title(self) -> None:
        branch_target_fact = _make_fact(
            "ERROR",
            message="Branch validation failed.",
            source="AGGREGATE",
            contexts=["BRANCH_SOURCE"],
            group="TARGET",
        )
        rv = _make_rule_validation(
            "BLOCK",
            title="Issue status",
            error="Issue status failed",
            hint="Fix issue status",
            check_facts=[branch_target_fact],
        )
        result = _make_result(blocked=True, rule_validations=[rv])
        printer = ResultPrinter(
            output_levels=frozenset({OutputComponent.RULES_TITLE, OutputComponent.RULE_SUMMARY}),
            rich_enabled=False,
            severity_filter=SeverityFilter.SUCCESS,
        )

        _, err = _capture(printer, result)

        self.assertIn("  ✗ Rule: Issue status", err)
        self.assertIn("    Summary:     Branch validation failed.", err)
        self.assertNotIn("Error:   Issue status failed", err)
        self.assertNotIn("Hint:    Fix issue status", err)

    def test_pass_rule_does_not_print_error_or_hint(self) -> None:
        branch_target_fact = _make_fact(
            "SUCCESS",
            message="Branch validation passed.",
            source="AGGREGATE",
            contexts=["BRANCH_SOURCE"],
            group="TARGET",
        )
        rv = _make_rule_validation(
            "PASS",
            title="Issue status",
            error="Should not be printed",
            hint="Should also not be printed",
            success="Rule passed",
            check_facts=[branch_target_fact],
        )
        result = _make_result(blocked=False, rule_validations=[rv])
        printer = ResultPrinter(
            output_levels=frozenset({OutputComponent.RULES_META, OutputComponent.RULE_SUMMARY}),
            rich_enabled=False,
            severity_filter=SeverityFilter.SUCCESS,
        )

        out, _ = _capture(printer, result)

        self.assertIn("    Success:     Rule passed", out)
        self.assertIn("    Summary:     Branch validation passed.", out)
        self.assertNotIn("Should not be printed", out)
        self.assertNotIn("Should also not be printed", out)


class TestPrinterRuleTitleSpacing(unittest.TestCase):
    def test_title_only_output_has_no_blank_line_between_rules(self) -> None:
        first_fact = _make_fact(
            "SUCCESS",
            message="First branch validation passed.",
            source="AGGREGATE",
            contexts=["BRANCH_SOURCE"],
            group="TARGET",
        )
        second_fact = _make_fact(
            "ERROR",
            message="Second branch validation failed.",
            source="AGGREGATE",
            contexts=["BRANCH_SOURCE"],
            group="TARGET",
        )
        result = _make_result(
            blocked=True,
            rule_validations=[
                _make_rule_validation("PASS", title="Rule A", check_facts=[first_fact]),
                _make_rule_validation("BLOCK", title="Rule B", check_facts=[second_fact]),
            ],
        )
        printer = ResultPrinter(
            output_levels=frozenset({OutputComponent.RULES_TITLE}),
            rich_enabled=False,
            severity_filter=SeverityFilter.SUCCESS,
        )

        _, err = _capture(printer, result)

        self.assertIn("  ✓ Rule: Rule A\n  ✗ Rule: Rule B", err)
        self.assertNotIn("  ✓ Rule: Rule A\n\n  ✗ Rule: Rule B", err)

    def test_meta_output_has_no_blank_line_between_rule_titles(self) -> None:
        first_fact = _make_fact(
            "SUCCESS",
            message="First branch validation passed.",
            source="AGGREGATE",
            contexts=["BRANCH_SOURCE"],
            group="TARGET",
        )
        second_fact = _make_fact(
            "ERROR",
            message="Second branch validation failed.",
            source="AGGREGATE",
            contexts=["BRANCH_SOURCE"],
            group="TARGET",
        )
        result = _make_result(
            blocked=True,
            rule_validations=[
                _make_rule_validation("PASS", title="Rule A", success="OK", check_facts=[first_fact]),
                _make_rule_validation("BLOCK", title="Rule B", error="Broken", check_facts=[second_fact]),
            ],
        )
        printer = ResultPrinter(
            output_levels=frozenset({OutputComponent.RULES_TITLE, OutputComponent.RULES_META}),
            rich_enabled=False,
            severity_filter=SeverityFilter.SUCCESS,
        )

        _, err = _capture(printer, result)

        self.assertIn("  ✓ Rule: Rule A\n    Success:     OK\n  ✗ Rule: Rule B", err)
        self.assertNotIn("  ✓ Rule: Rule A\n    Success:     OK\n\n  ✗ Rule: Rule B", err)


class TestCurrentCommitPlaceholder(unittest.TestCase):
    def test_zero_commit_hash_is_rendered_as_current_commit(self) -> None:
        aggregate_fact = _make_fact(
            "ERROR",
            message="Commit validation failed because the commit 0000000000 was classified as invalid.",
            source="AGGREGATE",
            contexts=["COMMIT"],
            group="DETAIL",
        )
        commit_fact = _make_fact(
            "ERROR",
            message="Commit detail failed for 0000000000.",
            source="JQL",
            contexts=["COMMIT"],
            ref="0000000000",
            group="DETAIL",
        )
        result = _make_result(
            blocked=True,
            rule_validations=[_make_rule_validation("BLOCK", check_facts=[aggregate_fact, commit_fact])],
        )
        printer = ResultPrinter(
            output_levels=frozenset({OutputComponent.RULES_DETAILED}),
            rich_enabled=False,
            severity_filter=SeverityFilter.SUCCESS,
        )

        _, err = _capture(printer, result)

        self.assertIn("(current commit)", err)
        self.assertNotIn("0000000000", err)


# ---------------------------------------------------------------------------
# ResultPrinter — system checks always at end
# ---------------------------------------------------------------------------

class TestPrinterSystemChecks(unittest.TestCase):
    def _make_system_fact(self, source: str = "LICENSE") -> dict[str, object]:
        return _make_fact("ERROR", message="License invalid", source=source, contexts=["SYSTEM"])

    def test_system_fact_shown_in_small_mode(self) -> None:
        fact = self._make_system_fact("LICENSE")
        rv = _make_rule_validation("BLOCK", check_facts=[fact])
        result = _make_result(blocked=True, rule_validations=[rv])
        printer = ResultPrinter(output_levels=OUTPUT_SUMMARY, rich_enabled=False)
        _, err = _capture(printer, result)
        self.assertIn("License invalid", err)

    def test_system_fact_shown_in_rules_only_mode(self) -> None:
        fact = self._make_system_fact("JIRA_CONNECTION")
        rv = _make_rule_validation("BLOCK", check_facts=[fact])
        result = _make_result(blocked=True, rule_validations=[rv])
        printer = ResultPrinter(output_levels=OUTPUT_RULES_ONLY, rich_enabled=False)
        _, err = _capture(printer, result)
        self.assertIn("License invalid", err)

    def test_system_facts_deduplicated(self) -> None:
        fact1 = self._make_system_fact("LICENSE")
        fact2 = self._make_system_fact("LICENSE")
        rv = _make_rule_validation("BLOCK", check_facts=[fact1, fact2])
        result = _make_result(blocked=True, rule_validations=[rv])
        printer = ResultPrinter(output_levels=OUTPUT_SUMMARY, rich_enabled=False)
        _, err = _capture(printer, result)
        self.assertEqual(err.count("License invalid"), 1)

    def test_system_checks_appear_after_rules(self) -> None:
        sys_fact = self._make_system_fact("LICENSE")
        rv = _make_rule_validation("BLOCK", title="Some Rule", error="Rule error", check_facts=[sys_fact])
        result = _make_result(blocked=True, rule_validations=[rv])
        printer = ResultPrinter(output_levels=OUTPUT_RULES_DETAILED, rich_enabled=False)
        _, err = _capture(printer, result)
        rule_pos = err.find("Some Rule")
        sys_pos = err.find("License invalid")
        self.assertGreater(sys_pos, rule_pos)


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------

class TestParseResponse(unittest.TestCase):
    def test_blocked_result(self) -> None:
        data: dict[str, object] = {"result": "BLOCK", "ruleValidations": [], "errorValidations": []}
        cr = parse_response(data)
        self.assertTrue(cr.is_blocked())

    def test_pass_result(self) -> None:
        data: dict[str, object] = {"result": "PASS", "ruleValidations": [], "errorValidations": []}
        cr = parse_response(data)
        self.assertFalse(cr.is_blocked())

    def test_unknown_result_not_blocked(self) -> None:
        data: dict[str, object] = {"result": "UNKNOWN"}
        cr = parse_response(data)
        self.assertFalse(cr.is_blocked())

    def test_error_validations_are_parsed(self) -> None:
        data: dict[str, object] = {
            "result": "BLOCK",
            "ruleValidations": [],
            "errorValidations": [{"result": "BLOCK", "errorMessages": [{"text": "Backend exploded"}]}],
        }
        cr = parse_response(data)
        self.assertEqual(len(cr.error_validations), 1)

    def test_missing_result_defaults_to_unknown(self) -> None:
        cr = parse_response({})
        self.assertFalse(cr.is_blocked())

    def test_rule_validations_parsed(self) -> None:
        rv: dict[str, object] = {"ruleStatus": "PASS", "rule": {"title": "R"}, "checkFacts": [], "conditionFacts": []}
        data: dict[str, object] = {"result": "PASS", "ruleValidations": [rv]}
        cr = parse_response(data)
        self.assertEqual(len(cr.rule_validations), 1)

    def test_non_dict_items_in_rule_validations_ignored(self) -> None:
        data: dict[str, object] = {"result": "PASS", "ruleValidations": ["bad", 42, None]}
        cr = parse_response(data)
        self.assertEqual(len(cr.rule_validations), 0)


class TestPrinterErrorValidations(unittest.TestCase):
    def test_error_validations_are_printed(self) -> None:
        printer = ResultPrinter(output_levels=OUTPUT_SUMMARY, rich_enabled=False)
        result = CheckResult(
            result="BLOCK",
            rule_validations=[],
            error_validations=[
                {
                    "result": "BLOCK",
                    "successMessages": [],
                    "warningMessages": [],
                    "errorMessages": [{"text": "Backend exploded"}],
                    "detailMessages": [],
                }
            ],
        )

        _, err = _capture(printer, result)

        self.assertIn("Validation Errors", err)
        self.assertIn("Backend exploded", err)


class TestPrinterTimingStats(unittest.TestCase):
    def test_ignore_rules_are_counted_as_skipped(self) -> None:
        printer = ResultPrinter(output_levels=OUTPUT_SUMMARY, rich_enabled=False)
        result = _make_result(
            blocked=False,
            rule_validations=[
                _make_rule_validation("PASS", title="Rule 1"),
                _make_rule_validation("BLOCK", title="Rule 2"),
                _make_rule_validation("IGNORE", title="Rule 3"),
            ],
        )

        stats = compute_result_stats(result, is_visible=lambda _fact: True)

        self.assertEqual(stats["passed"], 1)
        self.assertEqual(stats["blocked"], 1)
        self.assertEqual(stats["skipped"], 1)

    def test_rules_skipped_by_condition_main_fact_are_counted_as_skipped(self) -> None:
        printer = ResultPrinter(output_levels=OUTPUT_SUMMARY, rich_enabled=False)
        skipped_condition_fact = _make_fact(
            "SKIP",
            message="Rule will be skipped based on the branch condition.",
            source="BRANCH_CONDITION",
            contexts=["BRANCH_SOURCE"],
            group="MAIN",
        )
        result = _make_result(
            blocked=False,
            rule_validations=[
                _make_rule_validation("PASS", title="Rule 1"),
                _make_rule_validation("BLOCK", title="Rule 2"),
                _make_rule_validation("PASS", title="Rule 3", condition_facts=[skipped_condition_fact]),
            ],
        )

        stats = compute_result_stats(result, is_visible=lambda _fact: True)

        self.assertEqual(stats["passed"], 1)
        self.assertEqual(stats["blocked"], 1)
        self.assertEqual(stats["skipped"], 1)


# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------
_CONFIG_ENV_KEYS = (
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


class TestLoadConfig(unittest.TestCase):
    def setUp(self) -> None:
        import os
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self._env_backup = {k: os.environ.pop(k) for k in _CONFIG_ENV_KEYS if k in os.environ}

    def tearDown(self) -> None:
        import os

        os.environ.update(self._env_backup)

    def _env_file(self, content: str) -> Path:
        p = Path(self._tmpdir) / "commit-check.env"
        p.write_text(content, encoding="utf-8")
        return p

    def test_loads_url_and_secret(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="https://example.com"\nJHFB_SECRET="abc"')
        cfg = load_config(f)
        self.assertEqual(cfg.url, "https://example.com")
        self.assertEqual(cfg.secret, "abc")

    def test_default_output_components(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"')
        cfg = load_config(f)
        self.assertEqual(
            cfg.output_levels,
            frozenset({
                OutputComponent.SUMMARY,
                OutputComponent.RULES_TITLE,
                OutputComponent.RULES_DETAILED,
            }),
        )

    def test_default_severity_filter_is_success(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"')
        cfg = load_config(f)
        self.assertEqual(cfg.severity_filter, SeverityFilter.SUCCESS)

    def test_output_summary_false_removes_small_output(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"\nJHFB_PRINT_SUMMARY="false"')
        cfg = load_config(f)
        self.assertNotIn(OutputComponent.SUMMARY, cfg.output_levels)

    def test_config_flags_can_disable_specific_output_parts(self) -> None:
        f = self._env_file(
            'JHFB_ENDPOINT="u"\n'
            'JHFB_SECRET="s"\n'
            'JHFB_PRINT_SUMMARY="true"\n'
            'JHFB_PRINT_RULE_META="false"\n'
            'JHFB_PRINT_RULE_DETAIL="false"\n'
        )
        cfg = load_config(f)
        self.assertIn(OutputComponent.SUMMARY, cfg.output_levels)
        self.assertIn(OutputComponent.RULES_TITLE, cfg.output_levels)
        self.assertNotIn(OutputComponent.RULES_META, cfg.output_levels)
        self.assertNotIn(OutputComponent.RULE_SUMMARY, cfg.output_levels)
        self.assertNotIn(OutputComponent.RULES_DETAILED, cfg.output_levels)

    def test_meta_enables_title_implicitly(self) -> None:
        f = self._env_file(
            'JHFB_ENDPOINT="u"\n'
            'JHFB_SECRET="s"\n'
            'JHFB_PRINT_SUMMARY="true"\n'
            'JHFB_PRINT_RULE_TITLE="false"\n'
            'JHFB_PRINT_RULE_META="true"\n'
            'JHFB_PRINT_RULE_SUMMARY="false"\n'
        )
        cfg = load_config(f)
        self.assertIn(OutputComponent.RULES_TITLE, cfg.output_levels)
        self.assertIn(OutputComponent.RULES_META, cfg.output_levels)

    def test_summary_enables_title_implicitly(self) -> None:
        f = self._env_file(
            'JHFB_ENDPOINT="u"\n'
            'JHFB_SECRET="s"\n'
            'JHFB_PRINT_SUMMARY="true"\n'
            'JHFB_PRINT_RULE_TITLE="false"\n'
            'JHFB_PRINT_RULE_META="false"\n'
            'JHFB_PRINT_RULE_SUMMARY="true"\n'
        )
        cfg = load_config(f)
        self.assertIn(OutputComponent.RULES_TITLE, cfg.output_levels)
        self.assertIn(OutputComponent.RULE_SUMMARY, cfg.output_levels)

    def test_all_output_flags_false_disables_output(self) -> None:
        f = self._env_file(
            'JHFB_ENDPOINT="u"\n'
            'JHFB_SECRET="s"\n'
            'JHFB_PRINT_SUMMARY="false"\n'
            'JHFB_PRINT_RULE_TITLE="false"\n'
            'JHFB_PRINT_RULE_META="false"\n'
            'JHFB_PRINT_RULE_SUMMARY="false"\n'
            'JHFB_PRINT_RULE_DETAIL="false"\n'
        )
        cfg = load_config(f)
        self.assertEqual(cfg.output_levels, frozenset({OutputComponent.DISABLED}))

    def test_custom_severity_filter_parsed(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"\nJHFB_SEVERITY_FILTER="WARNING"')
        cfg = load_config(f)
        self.assertEqual(cfg.severity_filter, SeverityFilter.WARNING)

    def test_env_var_overrides_file(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="file-url"\nJHFB_SECRET="s"')
        with patch.dict("os.environ", {"JHFB_ENDPOINT": "env-url"}):
            cfg = load_config(f)
        self.assertEqual(cfg.url, "env-url")

    def test_env_var_overrides_output_config_flags(self) -> None:
        f = self._env_file(
            'JHFB_ENDPOINT="u"\n'
            'JHFB_SECRET="s"\n'
            'JHFB_PRINT_SUMMARY="true"\n'
            'JHFB_PRINT_RULE_META="false"\n'
        )
        with patch.dict("os.environ", {"JHFB_PRINT_RULE_META": "true"}):
            cfg = load_config(f)
        self.assertTrue(cfg.output_config.rule_meta)
        self.assertIn(OutputComponent.RULES_META, cfg.output_levels)

    def test_rich_output_defaults_to_true(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"')
        cfg = load_config(f)
        self.assertTrue(cfg.rich_output)

    def test_show_conditions_defaults_to_false(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"')
        cfg = load_config(f)
        self.assertFalse(cfg.show_conditions)

    def test_show_conditions_true_is_parsed(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"\nJHFB_PRINT_CONDITIONS="true"')
        cfg = load_config(f)
        self.assertTrue(cfg.show_conditions)

    def test_show_conditions_false_is_parsed(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"\nJHFB_PRINT_CONDITIONS="false"')
        cfg = load_config(f)
        self.assertFalse(cfg.show_conditions)

    def test_rich_output_false_is_parsed(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"\nJHFB_RICH_OUTPUT="false"')
        cfg = load_config(f)
        self.assertFalse(cfg.rich_output)

    def test_locale_is_parsed(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"\nJHFB_LOCALE="de-DE"')
        cfg = load_config(f)
        self.assertEqual(cfg.locale, "de-DE")

    def test_locale_alias_is_normalized(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"\nJHFB_LOCALE="de_de"')
        cfg = load_config(f)
        self.assertEqual(cfg.locale, "de-DE")

    def test_missing_file_without_env_raises(self) -> None:
        with self.assertRaises(ConfigNotFoundError):
            load_config(Path(self._tmpdir) / "nonexistent.env")

    def test_missing_secret_raises(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"')
        with self.assertRaises(ConfigMissingKeyError):
            load_config(f)

    def test_invalid_severity_filter_raises(self) -> None:
        f = self._env_file('JHFB_ENDPOINT="u"\nJHFB_SECRET="s"\nJHFB_SEVERITY_FILTER="BROKEN"')
        with self.assertRaises(ConfigInvalidValueError):
            load_config(f)

    def test_comments_and_blank_lines_ignored(self) -> None:
        f = self._env_file("# comment\n\nJHFB_ENDPOINT=u\nJHFB_SECRET=s\n# another comment\n")
        cfg = load_config(f)
        self.assertEqual(cfg.url, "u")


class TestLoadConfigOrSkip(unittest.TestCase):
    def test_missing_required_key_is_reported_without_traceback(self) -> None:
        import tempfile
        from jhfb_hooks.runner import load_config_or_skip

        with tempfile.TemporaryDirectory() as tmpdir:
            hook_dir = Path(tmpdir)
            (hook_dir / "commit-check.env").write_text('JHFB_ENDPOINT="u"\n', encoding="utf-8")
            out = io.StringIO()
            err = io.StringIO()
            with patch.object(sys, "stdout", out), patch.object(sys, "stderr", err):
                cfg = load_config_or_skip(hook_dir)

        self.assertIsNone(cfg)
        self.assertIn("Skipping local commit check", err.getvalue())
        self.assertIn("Missing required key", err.getvalue())

    def test_invalid_severity_value_is_reported_without_traceback(self) -> None:
        import tempfile
        from jhfb_hooks.runner import load_config_or_skip

        with tempfile.TemporaryDirectory() as tmpdir:
            hook_dir = Path(tmpdir)
            (hook_dir / "commit-check.env").write_text(
                'JHFB_ENDPOINT="u"\nJHFB_SECRET="s"\nJHFB_SEVERITY_FILTER="BROKEN"\n',
                encoding="utf-8",
            )
            out = io.StringIO()
            err = io.StringIO()
            with patch.object(sys, "stdout", out), patch.object(sys, "stderr", err):
                cfg = load_config_or_skip(hook_dir)

        self.assertIsNone(cfg)
        self.assertIn("Skipping local commit check", err.getvalue())
        self.assertIn("Invalid value for JHFB_SEVERITY_FILTER", err.getvalue())


if __name__ == "__main__":
    unittest.main()
