# Day 13 Checklist — Fault classification + accuracy (the headline feature)

**Goal for today:** teach the harness to look at a failed case and say *why* it
failed — **device fault** (modem answered, but wrong/garbled/dropped), **timeout**
(no answer in time), or **harness fault** (the failure was on *our* side). Then
prove it works by running known injected faults and computing a **classification
accuracy** number. This is the differentiator: separating "the device is broken"
from "our test rig is broken" is exactly what validation teams pay for.

**Time:** ~4 hours (the most important harness day). **Prereqs:** Day 12 done, 72
tests, CI green.

> Code blocks start at the left margin. No new dependencies.

---

## Background knowledge (read before you build)

### 1. Why classify faults at all

When a conformance test fails, the first question in the lab is always: *is it the
device under test, or is it our setup?* Blaming the device for a failure that was
really a loose cable or a bad test script wastes everyone's time and erodes trust in
the harness. A harness that can say **"this failure is the device's fault"** vs
**"this one is ours"** is dramatically more useful than one that just says "failed."
This triage is the core skill this whole project demonstrates.

### 2. The categories, and how we tell them apart

| Category | Meaning | How the harness detects it |
|---|---|---|
| `PASS` | the case succeeded | response matched the expectation |
| `DEVICE_FAULT` | modem reachable, but answered wrong / garbled / dropped | got a response (or a clean close), but it didn't match |
| `TIMEOUT` | no response within the time window | the read hit its deadline (`TimeoutError`) |
| `HARNESS_FAULT` | the failure was on *our* side | a non-timeout error (couldn't connect, our own bug) |

The classifier is **rule-based** and the *order of checks matters*: pass first, then
our-own-error, then timeout, then (by elimination) device fault. Each check is a
clean, defensible signal — not a guess.

### 3. Distinguishing "our error" from "device behavior"

The key new mechanism: the runner now catches **non-timeout exceptions** (like a
connection error) separately and records them as a `harness_error`. A `TimeoutError`
means *the device didn't answer* (device/timeout); a `ConnectionRefusedError` means
*we couldn't even reach it* (our side). Same failure on the surface, opposite blame —
and the harness keeps them apart.

### 4. Measuring a classifier (ground truth + accuracy)

How do you know the classifier is any good? You test it against **known** faults.
We build a set of scenarios where we *injected* the fault ourselves, so we know the
true category (the "ground truth"). We run each, classify the outcome, and compute
**accuracy = correct / total**. This is the same idea as evaluating any
classifier on a labeled test set — and it turns "I built a classifier" into "I built
a classifier and measured it at X% accuracy across N scenarios," which is a far
stronger claim.

---

## Part A — The classifier + a harness-error signal

### 1. Add `harness_error` to `CaseResult` (`harness/runner.py`)

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
    duration_ms: float = 0.0
    harness_error: str = ""    # set when the failure was on OUR side (not the device)
    reason: str = ""
```

### 2. Make `run_case` catch our-side errors (`harness/runner.py`)

Replace `run_case` with this version. It adds a broad `except` (for the send loop
and preconditions) that records a **harness error** and stops retrying — a
connection/our-bug failure won't fix itself:

```python
def run_case(case, transport, backoff_base: float = 0.05) -> CaseResult:
    """Run one case with retries; separate device faults, timeouts, and OUR errors."""
    start = time.monotonic()
    timeout = case.timeout_ms / 1000.0
    max_attempts = case.retries + 1

    def _elapsed_ms():
        return (time.monotonic() - start) * 1000

    # Preconditions (best effort). A non-timeout error here is on our side.
    for pre in case.precondition:
        try:
            transport.send(pre, timeout=timeout)
        except TimeoutError:
            log.warning("case=%r precondition %r timed out", case.name, pre)
        except Exception as e:
            log.error("case=%r precondition %r errored: %s", case.name, pre, e)
            return CaseResult(case.name, False, case.send, "", attempts=1,
                              harness_error=f"{type(e).__name__}: {e}",
                              duration_ms=_elapsed_ms(),
                              reason=f"precondition error: {e}")

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
                return CaseResult(case.name, True, case.send, response,
                                  attempts=attempt, duration_ms=_elapsed_ms())
        except TimeoutError:
            timed_out = True
            last_response, last_reason = "", f"timed out after {timeout:.2f}s"
            log.warning("case=%r attempt=%d/%d TIMEOUT sent=%r",
                        case.name, attempt, max_attempts, case.send)
        except Exception as e:
            # Non-timeout error = OUR side (connection/bug). Don't retry.
            log.error("case=%r HARNESS ERROR sent=%r: %s", case.name, case.send, e)
            return CaseResult(case.name, False, case.send, "", attempts=attempt,
                              harness_error=f"{type(e).__name__}: {e}",
                              duration_ms=_elapsed_ms(),
                              reason=f"{type(e).__name__}: {e}")

        if attempt < max_attempts:
            time.sleep(backoff_base * (2 ** (attempt - 1)))

    return CaseResult(case.name, False, case.send, last_response, attempts=max_attempts,
                      timed_out=timed_out, duration_ms=_elapsed_ms(), reason=last_reason)
```

### 3. Create `harness/classifier.py`

```python
"""
classifier.py — Classify WHY a test case turned out the way it did.

Four labels (one success, three failure kinds):
  PASS          - the case matched its expectation.
  DEVICE_FAULT  - the modem was reachable but answered wrong / garbled / dropped.
  TIMEOUT       - no response arrived within the case's time window.
  HARNESS_FAULT - the failure was on OUR side (couldn't connect, our own bug).

Telling a DEVICE_FAULT from a HARNESS_FAULT is the core value of the project: when a
test fails, whose problem is it — the device's, or ours? The classifier is
rule-based, and the ORDER of the checks matters.
"""

from enum import Enum


class FaultCategory(Enum):
    PASS = "pass"
    DEVICE_FAULT = "device_fault"
    TIMEOUT = "timeout"
    HARNESS_FAULT = "harness_fault"


def classify(result) -> FaultCategory:
    """Label a CaseResult. Checks are ordered from most to least certain."""
    if result.passed:
        return FaultCategory.PASS
    if result.harness_error:            # we recorded an our-side error -> ours
        return FaultCategory.HARNESS_FAULT
    if result.timed_out:                # no response in the window
        return FaultCategory.TIMEOUT
    return FaultCategory.DEVICE_FAULT    # reachable, but the answer was wrong
```

- [ ] `runner.py` updated (`harness_error` field + broad `except`); `classifier.py`
      created.

---

## Part B — Fold classification into the report

Edit `harness/report.py` so each case is labeled and the totals include a
per-category breakdown.

**1. Import the classifier** (top of the file):

```python
from harness.classifier import classify
```

**2. Update `build_summary`** to classify each result:

```python
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
```

- [ ] `report.py` labels each case and adds `by_category` to the totals.

---

## Part C — The accuracy self-check (the headline number)

Create `harness/selfcheck.py`. It runs known injected faults and measures how often
the classifier gets the label right.

```python
"""
selfcheck.py — Measure the fault CLASSIFIER's accuracy against KNOWN faults.

For each scenario we inject a fault ourselves, so we know the true category (the
"ground truth"). We run it, classify the outcome, and compare. Accuracy =
correct / total. This is the headline metric: how reliably the harness tells device
faults, timeouts, and harness faults apart.

Run against a live simulator:  python -m harness.selfcheck
"""

import argparse
from dataclasses import dataclass

from harness.testplan import TestCase
from harness.transport import TcpTransport
from harness.runner import run_case, CaseResult
from harness.classifier import classify, FaultCategory


@dataclass
class Scenario:
    name: str
    fault: str                 # AT+FAULT mode to set first ("none" = healthy)
    send: str
    expect: str
    expected: FaultCategory    # the true label (ground truth)
    break_transport: bool = False   # if True, aim at a dead port (a harness fault)


SCENARIOS = [
    Scenario("healthy",       "none",       "AT",       "OK",    FaultCategory.PASS),
    Scenario("lying modem",   "wrongstate", "AT+BOGUS", "ERROR", FaultCategory.DEVICE_FAULT),
    Scenario("garbled reply", "malformed",  "AT",       "OK",    FaultCategory.DEVICE_FAULT),
    Scenario("dropped conn",  "dropout",    "AT",       "OK",    FaultCategory.DEVICE_FAULT),
    Scenario("too slow",      "delay",      "AT",       "OK",    FaultCategory.TIMEOUT),
    Scenario("cant connect",  "none",       "AT",       "OK",    FaultCategory.HARNESS_FAULT,
             break_transport=True),
]


def run_scenario(sc: Scenario, host: str, port: int) -> FaultCategory:
    # For the harness-fault scenario, aim at a dead port so connecting fails on OUR side.
    target_port = 1 if sc.break_transport else port
    transport = TcpTransport(host, target_port, timeout=0.5)
    try:
        transport.open()
    except Exception as e:
        # Couldn't even connect -> our side.
        result = CaseResult(sc.name, False, sc.send, "",
                            harness_error=f"{type(e).__name__}: {e}")
        return classify(result)
    try:
        transport.send("ATE0")
        if sc.fault != "none":
            transport.send(f"AT+FAULT={sc.fault}")
        case = TestCase(name=sc.name, send=sc.send, expect=sc.expect, timeout_ms=500)
        result = run_case(case, transport)
    finally:
        transport.close()
    return classify(result)


def run_selfcheck(host: str, port: int):
    """Run all scenarios; return (accuracy_pct, rows) where each row is
    (name, expected, got, correct)."""
    rows = []
    for sc in SCENARIOS:
        got = run_scenario(sc, host, port)
        rows.append((sc.name, sc.expected.value, got.value, got == sc.expected))
    correct = sum(1 for r in rows if r[3])
    accuracy = correct / len(rows) * 100 if rows else 0.0
    return accuracy, rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure fault-classification accuracy.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args(argv)

    accuracy, rows = run_selfcheck(args.host, args.port)
    print("\n=== Fault classification self-check ===")
    for name, expected, got, ok in rows:
        print(f"  [{'OK' if ok else 'XX'}] {name:14s} expected={expected:13s} got={got}")
    correct = sum(1 for r in rows if r[3])
    print(f"classification accuracy: {accuracy:.0f}% ({correct}/{len(rows)})")
    return 0 if accuracy == 100 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] `harness/selfcheck.py` created.

---

## Part D — Run the self-check live

Simulator in one terminal, self-check in another:

```bash
python -m simulator.server          # terminal 1 (fresh server!)
python -m harness.selfcheck         # terminal 2
```

- ✅ *Worked when:* you see all six scenarios labeled correctly and
  `classification accuracy: 100% (6/6)`. This line is your headline metric — the
  harness correctly tells device faults, a timeout, a harness fault, and a healthy
  case apart.

---

## Part E — Tests

**1. Create `test_classifier.py`** (unit tests for the labels + a real harness-error
path):

```python
"""
test_classifier.py — Unit tests for the fault classifier and its accuracy.
"""

from harness.runner import CaseResult, run_case
from harness.transport import Transport
from harness.testplan import TestCase
from harness.classifier import classify, FaultCategory


def _result(**kw):
    base = dict(name="x", passed=False, sent="AT", response="")
    base.update(kw)
    return CaseResult(**base)


def test_pass_is_pass():
    assert classify(_result(passed=True, response="OK")) == FaultCategory.PASS


def test_wrong_response_is_device_fault():
    assert classify(_result(response="WRONG")) == FaultCategory.DEVICE_FAULT


def test_no_response_is_timeout():
    assert classify(_result(timed_out=True)) == FaultCategory.TIMEOUT


def test_our_error_is_harness_fault():
    assert classify(_result(harness_error="ConnectionRefusedError: nope")) \
        == FaultCategory.HARNESS_FAULT


class _DeadTransport(Transport):
    """A transport whose send always fails on our side (a connection error)."""
    def open(self): pass
    def close(self): pass
    def send(self, command, timeout=2.0):
        raise ConnectionResetError("boom")


def test_connection_error_classifies_as_harness_fault():
    result = run_case(TestCase(name="t", send="AT", expect="OK"),
                      _DeadTransport(), backoff_base=0)
    assert classify(result) == FaultCategory.HARNESS_FAULT
```

**2. Create `test_selfcheck.py`** (the accuracy metric, against the live simulator via
the shared fixture):

```python
"""
test_selfcheck.py — The classifier scores 100% on known injected faults.
"""

from harness.selfcheck import run_selfcheck


def test_classification_accuracy_is_perfect(modem_address):
    host, port = modem_address
    accuracy, rows = run_selfcheck(host, port)
    assert accuracy == 100, rows      # rows shown on failure for debugging
```

**Run everything:**

```bash
pytest
```

- ✅ *Worked when:* all pass — 72 + 5 classifier + 1 selfcheck = **78 passed**.
  (`test_selfcheck` takes ~1s: the delay/timeout scenarios.)

---

## Part F — Docker sanity + push

```bash
docker build -t modem-harness . && docker run --rm modem-harness
git add -A
git commit -m "Day 13: fault classifier (device/timeout/harness) + accuracy self-check; classify in report"
git push
```

- ✅ **DAY 13 IS DONE when:** CI is green with 78 tests and
  `python -m harness.selfcheck` reports 100% classification accuracy.

---

## If something breaks

- **`test_selfcheck` accuracy < 100:** run `python -m harness.selfcheck` and read the
  `[XX]` rows — each shows expected vs got. Usually the delay scenario (needs client
  timeout 0.5s < server delay 3s) or the harness scenario (needs the dead port to
  refuse).
- **Harness scenario labeled DEVICE_FAULT instead of HARNESS_FAULT:** connecting to
  the dead port must raise (ConnectionRefused). If port 1 behaves oddly on your
  machine, use another closed port (e.g., 65535) in `run_scenario`.
- **`dropout` labeled TIMEOUT:** a clean connection close returns an empty string
  (not a `TimeoutError`), so it should be DEVICE_FAULT. If you see TIMEOUT, your
  `_read_response` may be raising on the empty read instead of returning "".
- **`test_report` broke:** `build_summary` now adds `category`/`by_category`; make
  sure you didn't remove an existing totals key. The old assertions still hold.
- **Circular import:** `classifier.py` must NOT import from `runner.py` (it only
  reads attributes off the result). `report.py` imports `classifier`, not vice versa.
- **CI red, local green:** confirm `runner.py`, `classifier.py`, `report.py`,
  `selfcheck.py`, `test_classifier.py`, and `test_selfcheck.py` were all committed.

---

## Progress log (updated as we go)

- ✅ **DAY 13 COMPLETE — the differentiator is built and measured.** Added
  `classifier.py` (device/timeout/harness labels), a `harness_error` signal in
  `run_case`, classification folded into the report (`by_category`), and
  `selfcheck.py`. Live self-check: **100% (6/6)** classification accuracy across all
  four labels. 78 tests green in Docker + CI.
- **Housekeeping caught afterward:** `.dockerignore` had been accidentally removed
  (via `git add -A` staging its deletion), so builds were copying `.venv` (context
  25MB). Diagnosed via the build-size jump + `git log -- .dockerignore`; restored it
  and added `results/`/caches.

---

*When CI is green with 78 tests and the self-check reports 100% accuracy, Day 13 is
done — the differentiator is built and measured. Day 14 turns all of this into a
polished report: JUnit XML (for CI) and an HTML conformance report that shows
pass/fail, the fault category per failure, and the run metrics.*
