# Day 11 Checklist — Grow the test suite to ~20 cases + a DRY cleanup

**Goal for today:** make the metrics *mean something* by growing the YAML suite from
9 cases to ~21, spanning all four feature areas — identity, registration
transitions, PDP context, and error handling — with both **positive** ("it works")
and **negative** ("it fails correctly") cases. Then a small **cleanup**: extract the
repeated "run a whole plan" logic into one function (DRY).

**Time:** ~2.5 hours (lighter, mostly writing YAML). **Prereqs:** Day 10 done, 53
tests, CI green.

> Code blocks start at the left margin.

---

## Background knowledge (read before you build)

### 1. Test coverage — breadth across features

"Coverage" means: are all the important behaviors exercised? A conformance suite
should touch every feature area and, within each, the meaningful cases — not ten
variations of the same easy path. Today we deliberately spread cases across
identity, registration, data (PDP), and errors so the pass rate reflects the *whole*
modem, not one corner.

### 2. Positive vs negative testing (the heart of conformance)

- **Positive test:** a valid action produces the right result (`AT+CGATT=1` when
  registered → `OK`).
- **Negative test:** an *invalid* action fails the *right way* (`AT+CGDCONT=99,...`
  → `ERROR`; `AT+CGATT=1` before registering → `ERROR`).

Conformance testing leans heavily on **negative** cases — proving a device rejects
what it should is often more important than proving it accepts what it should. Being
able to say "I test both the happy path and the failure path" is exactly the
mindset these roles want.

### 3. Test independence (order shouldn't matter)

Each case sets up the state it needs via its `precondition`, so cases don't depend
on running in a particular order or on leftovers from a previous case. Independent
tests can run in any order, in parallel, or alone — and a failure points at one
thing, not a chain. That's why, e.g., the "verbose error" case sets `AT+CMEE=2`
itself rather than assuming a prior case did.

### 4. DRY — don't repeat yourself

The "open a connection, disable echo, run every case in the plan" logic currently
lives in both `run.py` and (in spirit) the integration test. We'll pull the plan-run
loop into one `run_plan()` function so there's a single place that knows how to run
a plan. Less duplication = fewer places for bugs to hide and to change later.

---

## Part A — Expand the two existing plans

**Replace `testplans/identity.yaml`** (adds an IMSI-format case → 6 cases):

```yaml
name: Identity and info
description: Basic identity, SIM, and signal queries.
cases:
  - name: attention responds OK
    send: "AT"
    expect: "OK"

  - name: manufacturer identification
    send: "AT+CGMI"
    expect: "SimCorp"

  - name: model identification
    send: "AT+CGMM"
    expect: "SC-LTE-100"

  - name: IMSI is 15 digits
    send: "AT+CIMI"
    expect_regex: '\d{15}'

  - name: signal quality format
    send: "AT+CSQ"
    expect_regex: '\+CSQ: \d+,\d+'

  - name: SIM reports ready
    send: "AT+CPIN?"
    expect: "+CPIN: READY"
```

**Replace `testplans/registration.yaml`** (adds transitions → 7 cases):

```yaml
name: Registration state machine
description: Radio on/off, packet attach, and operator, with self-contained setup.
cases:
  - name: registered on home network by default
    send: "AT+CREG?"
    expect: "+CREG: 0,1"

  - name: radio off deregisters
    precondition:
      - "AT+CFUN=0"
    send: "AT+CREG?"
    expect: "+CREG: 0,0"

  - name: radio on re-registers
    precondition:
      - "AT+CFUN=0"
      - "AT+CFUN=1"
    send: "AT+CREG?"
    expect: "+CREG: 0,1"

  - name: cannot attach while not registered
    precondition:
      - "AT+CFUN=0"
    send: "AT+CGATT=1"
    expect: "ERROR"

  - name: attach succeeds once registered
    precondition:
      - "AT+CFUN=1"
    send: "AT+CGATT=1"
    expect: "OK"

  - name: losing registration clears the packet attach
    precondition:
      - "AT+CFUN=1"
      - "AT+CGATT=1"
      - "AT+CFUN=0"
    send: "AT+CGATT?"
    expect: "+CGATT: 0"

  - name: operator name shown when registered
    precondition:
      - "AT+CFUN=1"
    send: "AT+COPS?"
    expect: "SimCorp Telecom"
```

---

## Part B — Two new plans (PDP context + error handling)

**Create `testplans/pdp.yaml`** (4 cases):

```yaml
name: PDP context (data connection)
description: Define, list, and validate PDP contexts.
cases:
  - name: define a context returns OK
    send: 'AT+CGDCONT=1,"IP","internet"'
    expect: "OK"

  - name: defined context appears in the list
    precondition:
      - 'AT+CGDCONT=1,"IP","internet"'
    send: "AT+CGDCONT?"
    expect: '+CGDCONT: 1,"IP","internet"'

  - name: reject a context id out of range
    send: 'AT+CGDCONT=99,"IP","x"'
    expect: "ERROR"

  - name: test form lists supported values
    send: "AT+CGDCONT=?"
    expect: "+CGDCONT: (1-16)"
```

**Create `testplans/errors.yaml`** (4 cases):

```yaml
name: Error handling and verbosity
description: Unknown commands and AT+CMEE error-report modes (self-contained setup).
cases:
  - name: unknown command errors plainly
    precondition:
      - "AT+CMEE=0"
    send: "AT+BOGUS"
    expect: "ERROR"

  - name: verbose mode gives a text error
    precondition:
      - "AT+CMEE=2"
    send: "AT+BOGUS"
    expect: "+CME ERROR: unknown"

  - name: numeric mode gives a coded error
    precondition:
      - "AT+CMEE=1"
    send: "AT+BOGUS"
    expect: "+CME ERROR: 100"

  - name: CMEE read reports the mode
    precondition:
      - "AT+CMEE=2"
    send: "AT+CMEE?"
    expect: "+CMEE: 2"
```

- [ ] All four YAML files in place (`identity`, `registration`, `pdp`, `errors`).

**Heads-up — a Day 7 test hard-codes the identity count.** `test_harness.py`'s
`test_loads_identity_plan` asserts `len(plan.cases) == 5`. Now that identity has 6
cases, that test fails — correctly (it's a tripwire on the plan's shape). Make it
resilient instead of just bumping the number:

```python
def test_loads_identity_plan():
    plan = load_plan(TESTPLANS / "identity.yaml")
    assert isinstance(plan, TestPlan)
    assert plan.name == "Identity and info"
    assert len(plan.cases) >= 5                          # lower bound, not brittle
    assert any(c.send == "AT+CIMI" for c in plan.cases)  # a specific case exists
```

Lesson: an exact-count assertion breaks every time you add a case; assert on
*properties* you actually care about instead.

Note the mix of **positive** cases (define context → OK, attach when registered →
OK) and **negative** cases (bad cid → ERROR, attach when not registered → ERROR,
unknown command → ERROR). That balance is the point.

---

## Part C — Cleanup: extract `run_plan` (DRY)

**1. Add `run_plan` to `harness/runner.py`** (below `run_case`):

```python
def run_plan(plan, transport):
    """Run every case in `plan` over an already-open transport; return CaseResults.

    Sends ATE0 first so the modem doesn't echo commands back and clutter responses.
    This is the single place that knows how to run a whole plan — both the CLI and
    any future caller use it instead of re-implementing the loop.
    """
    transport.send("ATE0")
    return [run_case(case, transport) for case in plan.cases]
```

**2. Use it in `harness/run.py`.** Update the import and the per-plan loop:

```python
from harness.runner import run_case, run_plan
```

```python
    results = []
    for plan_path in plan_paths:
        plan = load_plan(plan_path)
        transport = TcpTransport(args.host, args.port)
        transport.open()
        try:
            results.extend(run_plan(plan, transport))   # was: send ATE0 + loop by hand
        finally:
            transport.close()
```

**3. Add a quick test for `run_plan`** in `test_runner.py` (uses the existing
`FakeTransport`):

```python
def test_run_plan_runs_every_case():
    from harness.runner import run_plan
    from harness.testplan import TestPlan

    plan = TestPlan(
        name="p", description="",
        cases=[_case(), _case(name="two", send="AT+CGMI", expect="Corp")],
    )
    # FakeTransport pops one response per send: ATE0, then each case.
    transport = FakeTransport(["OK", "OK", "SimCorp"])
    results = run_plan(plan, transport)
    assert len(results) == 2
    assert all(r.passed for r in results)
```

---

## Part D — Run everything and see the bigger numbers

**Unit + integration tests:**

```bash
pytest
```

- ✅ *Worked when:* all pass — the integration suite now runs **21** YAML cases, so
  the total is **66 passed** (29 simulator + 7 harness + 6 runner + 3 report + 21
  integration). Use `pytest -v` to see all 21 case names.

**Live conformance run** (simulator in one terminal, tool in another):

```bash
python -m simulator.server        # terminal 1
python -m harness.run             # terminal 2
```

- ✅ *Worked when:* the summary shows `cases=21 passed=21 ... pass_rate=100.0%`, and
  `results/summary.json` now details all 21 cases.

---

## Part E — Docker sanity + push

```bash
docker build -t modem-harness . && docker run --rm modem-harness
git add -A
git commit -m "Day 11: grow suite to 21 cases (identity/registration/pdp/errors, positive+negative); extract run_plan (DRY)"
git push
```

- ✅ **DAY 11 IS DONE when:** CI is green with 66 tests and a live run reports 21
  passing cases.

---

## If something breaks

- **A new YAML case fails:** run `python -m harness.run` with the simulator up and
  read the `reason` + `response` in `results/summary.json` — it tells you what came
  back vs what was expected.
- **`AT+CGDCONT=...` case fails on quotes:** the whole command must be single-quoted
  in YAML (`'AT+CGDCONT=1,"IP","internet"'`) so the inner double-quotes survive.
- **An error-mode case fails:** confirm the `precondition` sets the CMEE mode for
  *that* case — cases are independent and must not rely on a prior case's mode.
- **A case passes under `pytest` but fails under `python -m harness.run`:** the
  integration test uses a fresh connection PER CASE (isolated state), while the CLI
  uses one connection per plan (state carries between cases). A case that isn't
  self-sufficient (e.g. "operator shown when registered" with no `precondition`) can
  pass isolated but fail after a prior case left the modem deregistered. Fix: give
  the case a `precondition` that sets up the state it needs (`AT+CFUN=1`). Lesson: a
  non-independent case can hide behind an isolating runner — the realistic
  shared-connection run exposes it.
- **`test_run_plan_runs_every_case` fails:** the `FakeTransport` list must have one
  entry per send — one for `ATE0` plus one per case, in order.
- **Integration count isn't 21:** the test globs `testplans/*.yaml`; make sure all
  four files are there and parse (run `python -m harness.run` to surface any load
  error).
- **CI red, local green:** confirm the new/edited YAML files, `runner.py`, `run.py`,
  and `test_runner.py` were all committed (`git add -A`).

---

## Progress log (updated as we go)

- ✅ **DAY 11 COMPLETE — Phase 2 (harness) essentially done.** Grew the suite to 21
  cases across identity/registration/PDP/errors, balancing positive and negative
  tests. Extracted `run_plan` (DRY). 66 tests green in CI; live run reports 21/21.
- **Two lessons caught live:** (1) a brittle exact-count assertion broke when the
  plan grew — made it property-based. (2) A case passed under pytest (per-case
  connection) but failed under the CLI (shared connection) because it wasn't
  self-sufficient — added a `precondition`. That second one is a *harness* fault
  (bad test setup), not a *device* fault — the exact distinction Day 12–13 is about.

---

*When CI is green with 66 tests and 21 live cases, Day 11 is done — Phase 2 (the
harness) is essentially complete. Day 12 begins the differentiator: FAULT INJECTION
— teaching the (unfrozen-for-this-purpose) simulator to misbehave on command, so the
harness has real device faults to detect.*
