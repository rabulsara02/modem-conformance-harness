# Day 14 Checklist — JUnit XML + HTML conformance report

**Goal for today:** make the results *visible*. From the same summary you already
build, generate two reports: **JUnit XML** (the standard format CI tools read to
show pass/fail and annotate builds) and a self-contained **HTML report** (a clean
page anyone can open, showing each case's pass/fail, its **fault category**,
latency, and the run totals). Wire both into the `harness.run` CLI.

**Time:** ~3 hours. **Prereqs:** Day 13 done, 78 tests, CI green.

> Code blocks start at the left margin. No new dependencies (stdlib XML + HTML).

---

## Background knowledge (read before you build)

### 1. JUnit XML — the universal test-report format

Despite the name, **JUnit XML** isn't tied to Java — it's the de-facto standard
*schema* that CI systems (GitHub Actions, Jenkins, GitLab) understand. Emit your
results in it and the CI can show a pass/fail breakdown, annotate a pull request
with which cases failed, and track trends over time — all without knowing anything
about your harness. Producing a standard format is what makes your tool
*interoperable* instead of a black box.

Its shape is simple: a `<testsuite>` of `<testcase>` elements; a failing case gets a
`<failure>` child with a message. We'll tag each case's `classname` with its fault
category, so the category shows up in CI too.

### 2. HTML reporting — the human view

CI reads XML; people read a page. A self-contained **HTML report** (all CSS inline,
no external files) is portable — you can email it, commit it, or open it straight
from `results/`. It's what turns "78 tests pass" into something a hiring manager
browsing your repo can actually *see*.

### 3. One summary, many renderings (single source of truth)

Notice the pattern: `build_summary` produces the data *once*, and we render it three
ways — JSON (machines), JUnit XML (CI), HTML (humans). The data is computed in one
place; the reporters only *present* it. If the metrics change, every view updates
automatically. "One source of truth, multiple views" is a clean design point.

### 4. Escaping — don't let content break your output

A modem response can contain characters that are special in XML/HTML (`<`, `&`,
`"`). If you drop raw text into a page, those can corrupt the markup (or, in a web
context, enable injection). So we **escape** untrusted text: Python's
`xml.etree.ElementTree` escapes XML for us automatically, and we use `html.escape`
for the HTML. Being aware of escaping is a real security-hygiene signal.

---

## Part A — Add the two reporters to `harness/report.py`

**1. Add imports** at the top of `report.py`:

```python
import html
import xml.etree.ElementTree as ET
```

**2. Add `write_junit`** (JUnit XML from the summary):

```python
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
```

**3. Add `write_html`** (a self-contained HTML report):

```python
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
```

- [ ] `report.py` has `write_junit` and `write_html` (and the new imports).

---

## Part B — Emit both reports from the CLI

Edit `harness/run.py`.

**1. Update the import:**

```python
from harness.report import build_summary, write_summary, write_junit, write_html
```

**2. Add two CLI options** (next to `--out`):

```python
    parser.add_argument("--junit", default="results/junit.xml", help="JUnit XML output")
    parser.add_argument("--html", default="results/report.html", help="HTML report output")
```

**3. Write all three reports** (replace the single `write_summary` call):

```python
    summary = build_summary(results)
    write_summary(summary, args.out)
    write_junit(summary, args.junit)
    write_html(summary, args.html)
```

**4. Mention them in the printout** (after the summary line):

```python
    print(f"wrote {args.out}, {args.junit}, {args.html}")
```

- [ ] `run.py` writes JSON + JUnit + HTML.

---

## Part C — Generate a report and look at it

Simulator in one terminal, the tool in another:

```bash
python -m simulator.server        # terminal 1 (fresh)
python -m harness.run             # terminal 2
```

- [ ] Open `results/report.html` in your browser (`open results/report.html` on
      macOS). You should see the summary cards (cases, pass rate, etc.), the
      by-category line, and a table with a green `pass` badge on every row.
- [ ] Peek at `results/junit.xml` — a `<testsuite tests="21" failures="0">` with a
      `<testcase>` per case.

**See a fault in the report (optional but satisfying):** temporarily add a case to a
plan that triggers a fault, so a colored category badge appears. E.g. add to
`testplans/errors.yaml`:

```yaml
  - name: DEMO injected device fault
    precondition:
      - "AT+FAULT=wrongstate"
    send: "AT+BOGUS"
    expect: "ERROR"
```

Re-run `python -m harness.run`, refresh `report.html`, and that row shows an orange
`device_fault` badge (the modem lied `OK` instead of `ERROR`). **Delete the demo
case afterward** so the suite stays green.

---

## Part D — Tests

Add to `test_report.py`. **First**, update the existing `_r` helper (from Day 10)
to accept a `response` argument — the JUnit tests below use it:

```python
def _r(passed=True, attempts=1, timed_out=False, duration_ms=10.0, response="OK"):
    return CaseResult(
        name="x", passed=passed, sent="AT", response=response,
        attempts=attempts, timed_out=timed_out, duration_ms=duration_ms,
    )
```

Then add these tests:

```python
import xml.etree.ElementTree as ET

from harness.report import write_junit, write_html


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
```

**Run everything:**

```bash
pytest
```

- ✅ *Worked when:* all pass — 78 + 3 = **81 passed**.

---

## Part E — Docker sanity + push

`results/` is gitignored and dockerignored, so the generated reports won't be
committed or bloat the build.

```bash
docker build -t modem-harness . && docker run --rm modem-harness
git add -A
git commit -m "Day 14: JUnit XML + self-contained HTML conformance report (from one summary)"
git push
```

- ✅ **DAY 14 IS DONE when:** CI is green with 81 tests, and `python -m harness.run`
  writes `results/summary.json`, `results/junit.xml`, and a `results/report.html`
  you can open in a browser.

---

## If something breaks

- **`report.html` shows raw `&lt;` etc.:** that's correct escaped output for special
  characters; it renders fine in a browser. Don't "fix" it by removing `html.escape`.
- **JUnit XML won't parse:** a stray unescaped character usually — but ElementTree
  escapes for you, so check you built nodes with `ET.SubElement` (attributes/text),
  not by string-concatenating XML.
- **`open results/report.html` does nothing:** make sure the run actually produced it
  (the printout lists the paths); the folder is created automatically.
- **`test_junit_has_correct_counts` off by one:** `failures` counts cases where
  `passed` is False; a timed-out or wrong-response case counts as a failure.
- **CI red, local green:** confirm `report.py` and `run.py` (and the `test_report.py`
  additions) were committed.

---

## Progress log (updated as we go)

*(Fill in as you work through today.)*

---

*When CI is green with 81 tests and you can open a clean HTML report, Day 14 is done
— the work is now visible. Day 15 wires the whole thing into CI + Docker Compose so
the harness runs against the simulator automatically and publishes the report as a
build artifact.*
