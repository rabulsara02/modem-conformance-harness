"""
report.py — Aggregate CaseResults into a run summary and write it as JSON.

Single responsibility: it does NOT run tests or open sockets — it only turns a list
of results into a summary dict and persists it. That makes it trivially testable.
"""

import json
import html
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from harness.classifier import classify


def build_summary(results, plan_name: str = "all") -> dict:
    """Aggregate a list of CaseResult into a summary dict (JSON-serializable)."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    timed_out = sum(1 for r in results if r.timed_out)
    total_retries = sum(r.attempts - 1 for r in results)
    total_duration_ms = sum(r.duration_ms for r in results)
    pass_rate = (passed / total * 100) if total else 0.0

    # Classify every case and tag it; also count categories.
    by_category = {}
    cases_out = []
    for r in results:
        category = classify(r).value
        by_category[category] = by_category.get(category, 0) + 1
        row = asdict(r)
        row["category"] = category
        cases_out.append(row)

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
            "by_category": by_category,
        },
        "cases": cases_out,
    }


def write_summary(summary: dict, path) -> Path:
    """Write the summary dict to `path` as pretty JSON, creating dirs as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(summary, f, indent=2)
    return path


def write_junit(summary: dict, path) -> Path:
    """Write the summary as JUnit XML — the standard format CI tools consume.

    Each case becomes a <testcase>; a failing case gets a <failure> child whose
    `type` is the fault category. ElementTree escapes XML special characters for us.
    """
    totals = summary["totals"]
    testsuites = ET.Element("testsuites")
    suite = ET.SubElement(testsuites, "testsuite", {
        "name": str(summary.get("plan", "conformance")),
        "tests": str(totals["cases"]),
        "failures": str(totals["failed"]),
        "time": f"{totals['total_duration_ms'] / 1000:.3f}",
    })
    for c in summary["cases"]:
        case = ET.SubElement(suite, "testcase", {
            "name": c["name"],
            "classname": c.get("category", "case"),   # category shows up in CI
            "time": f"{c.get('duration_ms', 0) / 1000:.3f}",
        })
        if not c["passed"]:
            failure = ET.SubElement(case, "failure", {
                "message": c.get("reason", "") or "failed",
                "type": c.get("category", "failure"),
            })
            failure.text = f"sent={c['sent']!r} response={c['response']!r}"

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(testsuites).write(path, encoding="utf-8", xml_declaration=True)
    return path


# Category -> a color for the HTML badge.
_CATEGORY_COLOR = {
    "pass": "#1a7f37",
    "device_fault": "#b34700",
    "timeout": "#9a6700",
    "harness_fault": "#8250df",
}


def write_html(summary: dict, path) -> Path:
    """Write a self-contained HTML report (inline CSS, no external files)."""
    totals = summary["totals"]
    by_cat = totals.get("by_category", {})

    def esc(x):
        return html.escape(str(x))

    # Per-case rows.
    rows = []
    for c in summary["cases"]:
        category = c.get("category", "")
        label = "pass" if c["passed"] else category or "fail"
        color = _CATEGORY_COLOR.get(label, "#57606a")
        rows.append(
            "<tr>"
            f"<td>{esc(c['name'])}</td>"
            f"<td><code>{esc(c['sent'])}</code></td>"
            f"<td><span class='badge' style='background:{color}'>{esc(label)}</span></td>"
            f"<td>{c.get('duration_ms', 0):.2f}</td>"
            f"<td><code>{esc(c.get('response', ''))}</code></td>"
            "</tr>"
        )

    cat_summary = " · ".join(f"{esc(k)}: {esc(v)}" for k, v in by_cat.items()) or "—"

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Modem Conformance Report</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1f2328; }}
  h1 {{ margin-bottom: .25rem; }}
  .meta {{ color: #57606a; margin-bottom: 1.25rem; }}
  .cards {{ display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }}
  .card {{ border: 1px solid #d0d7de; border-radius: 8px; padding: .75rem 1rem; min-width: 8rem; }}
  .card .n {{ font-size: 1.6rem; font-weight: 700; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .92rem; }}
  th, td {{ text-align: left; padding: .45rem .6rem; border-bottom: 1px solid #eaecef; }}
  th {{ background: #f6f8fa; }}
  code {{ background: #f6f8fa; padding: 0 .25rem; border-radius: 4px; }}
  .badge {{ color: white; padding: .1rem .5rem; border-radius: 999px; font-size: .8rem; }}
</style></head><body>
  <h1>Modem Conformance Report</h1>
  <div class="meta">plan: {esc(summary.get('plan', 'all'))} · generated {esc(summary.get('generated_at', ''))}</div>
  <div class="cards">
    <div class="card"><div class="n">{totals['cases']}</div>cases</div>
    <div class="card"><div class="n">{totals['pass_rate_pct']}%</div>pass rate</div>
    <div class="card"><div class="n">{totals['failed']}</div>failed</div>
    <div class="card"><div class="n">{totals['total_retries']}</div>retries</div>
    <div class="card"><div class="n">{totals['total_duration_ms']}</div>ms total</div>
  </div>
  <div class="meta">by category: {cat_summary}</div>
  <table>
    <thead><tr><th>Case</th><th>Sent</th><th>Result</th><th>ms</th><th>Response</th></tr></thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
</body></html>"""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    return path