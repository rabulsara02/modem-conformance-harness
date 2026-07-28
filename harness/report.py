"""
report.py — Aggregate CaseResults into a run summary and write it as JSON.

Single responsibility: it does NOT run tests or open sockets — it only turns a list
of results into a summary dict and persists it. That makes it trivially testable.
"""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


def build_summary(results, plan_name: str = "all") -> dict:
    """Aggregate a list of CaseResult into a summary dict (JSON-serializable)."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    timed_out = sum(1 for r in results if r.timed_out)
    total_retries = sum(r.attempts - 1 for r in results)   # attempts beyond the first
    total_duration_ms = sum(r.duration_ms for r in results)
    pass_rate = (passed / total * 100) if total else 0.0

    return {
        "plan": plan_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "cases": total,
            "passed": passed,
            "failed": failed,
            "timed_out": timed_out,
            "total_retries": total_retries,
            "pass_rate_pct": round(pass_rate, 1),
            "total_duration_ms": round(total_duration_ms, 2),
        },
        "cases": [asdict(r) for r in results],   # per-case detail for the report
    }


def write_summary(summary: dict, path) -> Path:
    """Write the summary dict to `path` as pretty JSON, creating dirs as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(summary, f, indent=2)
    return path