# Day 10 Checklist — Metrics capture + a real conformance-report CLI

**Goal for today:** turn per-case results into **numbers**. Every run now records
per-case latency, aggregates a run summary (case counts, pass/fail, pass rate, total
retries, timeouts, duration), and writes it to a **machine-readable JSON file**.
You'll also build a **command-line tool** (`python -m harness.run`) that runs all
plans against a live simulator and prints + saves that summary.

These are the metrics that become your resume bullets — and the project's whole
philosophy is to instrument from the start, not retrofit numbers later.

**Time:** ~3.5 hours. **Prereqs:** Day 9 done, 50 tests, CI green.

> Code blocks start at the left margin. No new dependencies (all standard library).

---

## Background knowledge (read before you build)

### 1. Why a machine-readable summary (not just logs)

Logs are for *humans reading one run*. A **JSON summary** is for *machines*: CI can
gate on it, a dashboard can chart it over time, and Day 14's HTML/JUnit report is
generated from it. Emitting structured data (not just print statements) is what
lets the same run feed automation, reporting, and your resume. "I instrumented it
from the first run so I'd never have to invent numbers later" is a real answer to
"how do you know it works?"

### 2. What we measure, and what each number tells you

- **Cases / passed / failed** — the headline: did the modem conform?
- **Pass rate (%)** — normalized, comparable across runs of different sizes.
- **Per-case latency + total duration** — performance; also flags a command that
  got slow.
- **Total retries** — how much flakiness the run absorbed. Rising retries = a
  degrading device even if everything still "passes."
- **Timeouts** — the harshest failure; separated out because a no-response is
  different from a wrong-response (this distinction becomes fault *classification*
  on Day 12).

### 3. JSON + serialization

**JSON** is the universal data-interchange format (text, language-neutral). Python's
`json` module turns dicts/lists into it. `dataclasses.asdict()` converts a
`CaseResult` into a plain dict so it can be serialized — a clean bridge from your
typed objects to portable data.

### 4. Separation of concerns (three small pieces, one job each)

- **runner.py** — runs *one* case, returns a `CaseResult` (Day 8–9).
- **report.py** (new) — takes many results, computes the *summary*, writes JSON.
- **run.py** (new) — the *orchestrator/CLI*: connect, loop over plans, hand results
  to the report.

Each file has a single responsibility, so each is independently testable and
replaceable. This is the **single-responsibility principle** in practice.

### 5. A CLI with `argparse` + exit codes

`argparse` gives your tool real flags (`--host`, `--port`, `--out`) with help text
and validation for free. And the tool **returns an exit code**: `0` if everything
passed, non-zero if anything failed. That's how command-line tools talk to CI and
scripts — a green/red that automation can read. Knowing that exit codes drive CI is
a small but real systems detail.

### 6. Don't commit generated artifacts

The `results/summary.json` a run produces is an *output*, not source. We add
`results/` to `.gitignore` so generated files don't clutter the repo or cause noisy
diffs. (Committing build/output artifacts is a common rookie smell.)

---

## Part A — Add per-case latency to the runner

Edit `harness/runner.py`.

**1. Add a `duration_ms` field to `CaseResult`:**

```python
@dataclass
class CaseResult:
    """The outcome of running one test case."""
    name: str
    passed: bool
    sent: str
    response: str
    attempts: int = 1
    timed_out: bool = False
    duration_ms: float = 0.0   # wall-clock time to run this case (all attempts)
    reason: str = ""
```

**2. Time the case in `run_case`.** Capture a start time at the top and set
`duration_ms` at *both* return points. Replace the function body's start and its two
`return CaseResult(...)` lines so they read:

```python
def run_case(case, transport, backoff_base: float = 0.05) -> CaseResult:
    """Run one case: preconditions, then send-and-check with retries + backoff."""
    start = time.monotonic()
    timeout = case.timeout_ms / 1000.0
    max_attempts = case.retries + 1

    for pre in case.precondition:
        try:
            transport.send(pre, timeout=timeout)
        except TimeoutError:
            log.warning("case=%r precondition %r timed out", case.name, pre)

    last_response, last_reason, timed_out = "", "", False

    for attempt in range(1, max_attempts + 1):
        try:
            response = transport.send(case.send, timeout=timeout)
            timed_out = False
            passed, reason = _check(case, response)
            last_response, last_reason = response, reason
            log.info("case=%r attempt=%d/%d sent=%r passed=%s",
                     case.name, attempt, max_attempts, case.send, passed)
            if passed:
                return CaseResult(
                    case.name, True, case.send, response, attempts=attempt,
                    duration_ms=(time.monotonic() - start) * 1000,
                )
        except TimeoutError as e:
            timed_out = True
            last_response, last_reason = "", str(e)
            log.warning("case=%r attempt=%d/%d TIMEOUT sent=%r",
                        case.name, attempt, max_attempts, case.send)

        if attempt < max_attempts:
            time.sleep(backoff_base * (2 ** (attempt - 1)))

    return CaseResult(
        case.name, False, case.send, last_response, attempts=max_attempts,
        timed_out=timed_out, duration_ms=(time.monotonic() - start) * 1000,
        reason=last_reason,
    )
```

- [ ] `CaseResult` has `duration_ms`; `run_case` sets it at both returns.

---

## Part B — The report aggregator

Create `harness/report.py`:

```python
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
```

- [ ] `harness/report.py` created.

---

## Part C — The command-line runner

Create `harness/run.py`:

```python
"""
run.py — Run all YAML test plans against a modem and write a JSON summary.

Usage:
  python -m harness.run [--host H] [--port P] [--plans DIR] [--out FILE]

Assumes a simulator is reachable (start one with `python -m simulator.server`
or `docker compose up`). Exit code: 0 if all cases passed, 1 if any failed.
"""

import argparse
import logging
import sys
from pathlib import Path

from harness.testplan import load_plan
from harness.transport import TcpTransport
from harness.runner import run_case
from harness.report import build_summary, write_summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run modem conformance test plans.")
    parser.add_argument("--host", default="127.0.0.1", help="modem host")
    parser.add_argument("--port", type=int, default=5050, help="modem port")
    parser.add_argument("--plans", default="testplans", help="folder of YAML plans")
    parser.add_argument("--out", default="results/summary.json", help="summary output")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    plan_paths = sorted(Path(args.plans).glob("*.yaml"))
    if not plan_paths:
        print(f"No plans found in {args.plans!r}", file=sys.stderr)
        return 2

    results = []
    for plan_path in plan_paths:
        plan = load_plan(plan_path)
        transport = TcpTransport(args.host, args.port)
        transport.open()                       # one connection per plan
        try:
            transport.send("ATE0")             # clean, echo-free responses
            for case in plan.cases:
                results.append(run_case(case, transport))
        finally:
            transport.close()

    summary = build_summary(results)
    out = write_summary(summary, args.out)

    t = summary["totals"]
    print("\n=== Conformance summary ===")
    print(f"cases={t['cases']} passed={t['passed']} failed={t['failed']} "
          f"timed_out={t['timed_out']} retries={t['total_retries']} "
          f"pass_rate={t['pass_rate_pct']}% duration={t['total_duration_ms']}ms")
    print(f"wrote {out}")

    # Exit non-zero if anything failed, so CI / scripts can gate on it.
    return 0 if t["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] `harness/run.py` created.

---

## Part D — Run it live (see your first report)

You need a running simulator, then point the tool at it.

- [ ] Terminal 1 — start the simulator:

```bash
python -m simulator.server
```

- [ ] Terminal 2 — run the conformance tool:

```bash
python -m harness.run
```

- ✅ *Worked when:* you see a summary line like
  `cases=9 passed=9 failed=0 timed_out=0 retries=0 pass_rate=100.0% duration=…ms`
  and it reports `wrote results/summary.json`.

- [ ] Open `results/summary.json` and read it — totals block + a per-case list with
      `duration_ms`, `attempts`, etc. **This JSON is the artifact everything else
      (Day 14 report, your resume numbers) is built from.**

---

## Part E — Test the aggregator

Create `test_report.py` at the repo root (tests the summary math with fake results —
no server needed):

```python
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
```

**Run everything:**

```bash
pytest
```

- ✅ *Worked when:* all pass — 50 + 3 report tests = **53 passed**.

---

## Part F — Ignore generated output, sanity check, push

- [ ] Add generated results to `.gitignore` (append a line):

```
results/
```

- [ ] Docker sanity + push:

```bash
docker build -t modem-harness . && docker run --rm modem-harness
git add -A
git commit -m "Day 10: metrics summary (JSON) + conformance-report CLI (harness.run); ignore results/"
git push
```

- ✅ **DAY 10 IS DONE when:** CI is green with 53 tests, `python -m harness.run`
  prints a summary and writes `results/summary.json`, and `results/` is gitignored.

---

## If something breaks

- **`ConnectionRefusedError` from `python -m harness.run`:** no simulator is
  running — start `python -m simulator.server` (port 5050) first, or pass
  `--host/--port`.
- **`results/summary.json` not created:** `write_summary` makes the folder; check
  you didn't pass an `--out` path you can't write to. The default is
  `results/summary.json` under the repo.
- **`test_pass_rate_is_rounded` fails:** `round(66.666…, 1)` is `66.7`; make sure
  you're rounding the percentage, not the fraction.
- **Summary shows retries you didn't expect:** `total_retries` counts
  `attempts - 1` summed; a case that needed 2 attempts contributes 1.
- **`results/` still shows in `git status`:** confirm the `.gitignore` line is
  `results/` and that no summary file was already committed (`git rm --cached` it if
  so).
- **CI red, local green:** confirm `runner.py`, `report.py`, `run.py`, and
  `test_report.py` were committed.

---

## Progress log (updated as we go)

- ✅ **DAY 10 COMPLETE.** Added per-case latency, `report.py` (JSON summary
  aggregation), and a `harness.run` CLI with argparse + exit codes. First live run:
  `cases=9 passed=9 pass_rate=100.0% duration=1.62ms`, wrote `results/summary.json`.
  53 tests green in Docker + CI.
- **Bug caught + fixed:** the new field was named `duration` in `CaseResult` but
  referenced as `duration_ms` in `run_case`/`report.py` — Python's "Did you mean
  'duration'?" pinpointed it. Renamed to `duration_ms`.
- **Git lesson:** committed `results/summary.json` before gitignoring it; `.gitignore`
  doesn't untrack committed files, so used `git rm --cached` to stop tracking it.

---

*When CI is green with 53 tests and `harness.run` writes a JSON summary, Day 10 is
done — the tool now produces numbers. Day 11 grows the test suite toward ~20 cases
(more registration transitions, PDP context, error handling) so the metrics are
meaningful, and cleans up the harness code.*
