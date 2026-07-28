"""
test_report.py — Unit tests for the metrics aggregator (harness/report.py).
Builds CaseResults by hand so we can assert the summary math precisely.
"""

import json

from harness.runner import CaseResult
from harness.report import build_summary, write_summary


def _r(passed=True, attempts=1, timed_out=False, duration_ms=10.0):
    return CaseResult(
        name="x", passed=passed, sent="AT", response="OK",
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