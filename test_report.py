"""
test_report.py — Unit tests for the metrics aggregator (harness/report.py).
Builds CaseResults by hand so we can assert the summary math precisely.
"""

import json
import xml.etree.ElementTree as ET
from harness.runner import CaseResult
from harness.report import build_summary, write_summary, write_junit, write_html


def _r(passed=True, attempts=1, timed_out=False, duration_ms=10.0, response="OK"):
    return CaseResult(
        name="x", passed=passed, sent="AT", response=response,
        attempts=attempts, timed_out=timed_out, duration_ms=duration_ms,
    )


def test_summary_counts():
    results = [_r(), _r(passed=False), _r(attempts=3), _r(passed=False, timed_out=True)]
    totals = build_summary(results)["totals"]
    assert totals["cases"] == 4
    assert totals["passed"] == 2
    assert totals["failed"] == 2
    assert totals["timed_out"] == 1
    assert totals["total_retries"] == 2          # attempts=3 -> 2 retries; others 0


def test_pass_rate_is_rounded():
    results = [_r(), _r(), _r(passed=False)]      # 2 of 3
    assert build_summary(results)["totals"]["pass_rate_pct"] == 66.7


def test_write_summary_creates_file(tmp_path):
    summary = build_summary([_r()])
    out = write_summary(summary, tmp_path / "results" / "summary.json")
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["totals"]["cases"] == 1



def test_junit_has_correct_counts(tmp_path):
    summary = build_summary([_r(), _r(passed=False, response="WRONG")])
    out = write_junit(summary, tmp_path / "junit.xml")
    tree = ET.parse(out)
    suite = tree.getroot().find("testsuite")
    assert suite.get("tests") == "2"
    assert suite.get("failures") == "1"


def test_junit_marks_failures(tmp_path):
    summary = build_summary([_r(passed=False, response="WRONG")])
    out = write_junit(summary, tmp_path / "junit.xml")
    failures = ET.parse(out).getroot().iter("failure")
    assert any(f is not None for f in failures)


def test_html_contains_summary(tmp_path):
    summary = build_summary([_r(), _r()])
    out = write_html(summary, tmp_path / "report.html")
    text = out.read_text()
    assert "Modem Conformance Report" in text
    assert "pass rate" in text