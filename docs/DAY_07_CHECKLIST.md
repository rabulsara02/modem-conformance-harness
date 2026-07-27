# Day 7 Checklist — YAML test plans (Phase 2 begins: the harness)

**Goal for today:** design the format for **declarative test plans** — YAML files
that describe what to send the modem and what response to expect — and write a
**loader** that reads and validates them into Python objects. No test *runs* yet;
today is the data format and the parser. Tomorrow (Day 8) the driver reads these
plans and drives the simulator.

This is the start of the **conformance harness** — the actual product, and the part
that sells you for validation roles.

**Time:** ~3 hours. **Prereqs:** Phase 1 done (simulator frozen, 29 tests, CI green).

> Code blocks start at the left margin. New dependency today: PyYAML.

---

## Background knowledge (read before you build)

### 1. What YAML is, and why we use it for test plans

**YAML** is a human-readable data format (like JSON, but easier on the eyes — no
braces, indentation instead). A YAML test case looks like:

```yaml
- name: attention responds OK
  send: "AT"
  expect: "OK"
```

We define tests as **data** (YAML) rather than **code** (Python) on purpose. This
is **data-driven testing**, and the payoff is big:

- **Anyone can add a test** by editing YAML — no Python needed. A hardware engineer
  who doesn't code can contribute test cases.
- **The tests and the engine are separate.** One driver runs hundreds of cases;
  adding a case never touches the driver.
- **Plans are portable and reviewable** — they read like a test specification, which
  is exactly what a conformance test plan *is*.

"I made the test cases declarative data so the plan is separate from the engine
that runs it" is a strong design sentence for a test-engineering interview.

### 2. The schema we're designing

Each **case** has these fields (only `name`, `send`, and one `expect*` are
required):

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Human label, shown in reports |
| `send` | yes | The AT command to send |
| `expect` | one of | Substring the response must **contain** |
| `expect_regex` | these two | Regex the response must **match** |
| `timeout_ms` | no (def 2000) | How long to wait before failing |
| `retries` | no (def 0) | How many times to retry on failure |
| `precondition` | no (def none) | Commands to send first to set up state |

`expect` (substring) vs `expect_regex` (regex) covers both "the reply contains this
text" and "the reply matches this pattern" (e.g. signal quality is
`+CSQ: <digits>,<digits>`, which needs a regex).

### 3. `yaml.safe_load` vs `yaml.load` (a security habit)

Always parse external YAML with **`yaml.safe_load`**, never `yaml.load`. Plain
`load` can construct arbitrary Python objects encoded in the file — a remote-code
risk if the file isn't fully trusted. `safe_load` only builds basic types (dicts,
lists, strings, numbers). Knowing this distinction is a real security-awareness
signal.

### 4. Fail LOUDLY here (the opposite of the simulator)

Notice the deliberate contrast with Day 6:

- The **simulator** fails *gracefully* on bad input — it models a device receiving
  hostile data and must never crash.
- The **loader** fails *loudly* — if a test plan is malformed (missing `send`, no
  `expect`), we `raise ValueError` with a clear message. A broken plan is a
  *developer* error we want surfaced immediately, not swallowed.

Matching the error strategy to the situation — graceful for untrusted input, loud
for developer config — is a nuance worth being able to explain.

### 5. Two pytest features you'll meet today

- **`pytest.raises(...)`** — asserts that a block *does* raise a given exception.
  We use it to prove the loader rejects bad plans.
- **`tmp_path`** — a pytest fixture that hands your test a fresh temporary
  directory. We write a deliberately broken YAML file there and confirm the loader
  rejects it, without cluttering the repo.

---

## Part A — Add PyYAML and build the loader

### 1. Add the dependency

Add PyYAML to `requirements.txt` (so it now has two lines):

```
pytest==9.1.1
PyYAML==6.0.2
```

Then install it into your venv:

```bash
pip install -r requirements.txt
```

### 2. Create the harness package

Make a new package folder with two files:

```
harness/__init__.py     (marks the folder a package)
harness/testplan.py
```

For `harness/__init__.py`:

```python
"""harness — reads declarative YAML test plans and runs them against a modem."""
```

### 3. Write `harness/testplan.py`

```python
"""
testplan.py — Load and validate declarative YAML test plans.

A test PLAN is data, not code: a YAML file listing test CASES, each of which sends
an AT command and states what response to expect. The harness (Day 8) reads these
plans and drives the modem. Keeping tests as data means new tests are added by
editing YAML — no Python changes — and one driver runs them all.

Error-handling contrast (deliberate):
  - The SIMULATOR fails GRACEFULLY on bad input (never crash) — it models a device
    under test receiving hostile input.
  - This LOADER fails LOUDLY (raises ValueError) on a malformed plan — a broken
    plan is a developer mistake we want surfaced immediately.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class TestCase:
    """One test: send a command, check the response.

    (`__test__ = False` tells pytest this is a domain model, not a test class —
    pytest otherwise tries to collect any class named Test* and warns.)

    name         : human label for reports.
    send         : the AT command to send.
    expect       : substring the response must CONTAIN (optional).
    expect_regex : regex the response must MATCH (optional).
                   At least one of expect / expect_regex is required.
    timeout_ms   : how long to wait for a response before failing.
    retries      : how many times to retry on failure/timeout.
    precondition : commands to send first to set up state (e.g. "AT+CFUN=0").
    """
    __test__ = False   # not a pytest test class — this is a domain model
    name: str
    send: str
    expect: str | None = None
    expect_regex: str | None = None
    timeout_ms: int = 2000
    retries: int = 0
    precondition: list = field(default_factory=list)


@dataclass
class TestPlan:
    """A named collection of test cases loaded from one YAML file."""
    __test__ = False   # not a pytest test class — this is a domain model
    name: str
    description: str
    cases: list


def load_plan(path) -> TestPlan:
    """Read a YAML test plan from `path`, validate it, and return a TestPlan.

    Raises ValueError with a clear, located message if the plan is malformed.
    """
    path = Path(path)
    with path.open() as f:
        # safe_load only builds basic Python types; it will NOT execute arbitrary
        # objects the way yaml.load() can. Always use safe_load on files.
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be a mapping (name/description/cases)")

    name = raw.get("name")
    if not name:
        raise ValueError(f"{path}: missing required 'name'")
    description = raw.get("description", "")

    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{path}: 'cases' must be a non-empty list")

    cases = []
    for i, c in enumerate(raw_cases):
        where = f"{path} case #{i + 1}"
        if not isinstance(c, dict):
            raise ValueError(f"{where}: each case must be a mapping")
        if not c.get("name"):
            raise ValueError(f"{where}: missing 'name'")
        if not c.get("send"):
            raise ValueError(f"{where} ({c.get('name')}): missing 'send'")
        if c.get("expect") is None and c.get("expect_regex") is None:
            raise ValueError(f"{where} ({c['name']}): needs 'expect' or 'expect_regex'")

        cases.append(
            TestCase(
                name=c["name"],
                send=c["send"],
                expect=c.get("expect"),
                expect_regex=c.get("expect_regex"),
                timeout_ms=c.get("timeout_ms", 2000),
                retries=c.get("retries", 0),
                precondition=c.get("precondition", []),
            )
        )

    return TestPlan(name=name, description=description, cases=cases)
```

- [ ] PyYAML added to `requirements.txt` and installed.
- [ ] `harness/__init__.py` and `harness/testplan.py` created.

---

## Part B — Write example test plans

Create a `testplans/` folder with two example plans. These double as real,
runnable test plans once the driver exists (Day 8).

**`testplans/identity.yaml`:**

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

  - name: signal quality format
    send: "AT+CSQ"
    expect_regex: '\+CSQ: \d+,\d+'

  - name: SIM reports ready
    send: "AT+CPIN?"
    expect: "+CPIN: READY"
```

**`testplans/registration.yaml`:**

```yaml
name: Registration state machine
description: Radio on/off and packet-attach transitions.
cases:
  - name: registered on home network by default
    send: "AT+CREG?"
    expect: "+CREG: 0,1"

  - name: radio off deregisters
    precondition:
      - "AT+CFUN=0"
    send: "AT+CREG?"
    expect: "+CREG: 0,0"

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
```

- [ ] Both YAML files created under `testplans/`.

Note: each case's `precondition` sets up the state it needs, so cases don't depend
on run order. We'll finalize execution semantics (fresh state per case) on Day 8.

---

## Part C — Test the loader

Create `test_harness.py` at the repo root:

```python
"""
test_harness.py — Tests for the YAML test-plan loader (harness/testplan.py).

Covers: loading real example plans, default values, and — importantly — that the
loader REJECTS malformed plans loudly (the opposite of the simulator's graceful
handling). Uses pytest.raises (assert an exception happens) and tmp_path (a fresh
temp directory) to test the rejection cases without touching the repo.
"""

from pathlib import Path

import pytest

from harness.testplan import load_plan, TestPlan

TESTPLANS = Path(__file__).parent / "testplans"


def test_loads_identity_plan():
    plan = load_plan(TESTPLANS / "identity.yaml")
    assert isinstance(plan, TestPlan)
    assert plan.name == "Identity and info"
    assert len(plan.cases) == 5
    assert plan.cases[0].send == "AT"


def test_defaults_are_applied():
    case = load_plan(TESTPLANS / "identity.yaml").cases[0]
    assert case.timeout_ms == 2000     # default
    assert case.retries == 0           # default
    assert case.precondition == []     # default


def test_regex_field_is_parsed():
    plan = load_plan(TESTPLANS / "identity.yaml")
    signal = next(c for c in plan.cases if c.name == "signal quality format")
    assert signal.expect_regex is not None


def test_registration_plan_has_preconditions():
    plan = load_plan(TESTPLANS / "registration.yaml")
    assert any(c.precondition for c in plan.cases)


def test_missing_send_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: bad\ncases:\n  - name: no send\n    expect: OK\n")
    with pytest.raises(ValueError):
        load_plan(bad)


def test_missing_expect_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: bad\ncases:\n  - name: no expect\n    send: AT\n")
    with pytest.raises(ValueError):
        load_plan(bad)


def test_empty_cases_is_rejected(tmp_path):
    bad = tmp_path / "empty.yaml"
    bad.write_text("name: empty\ncases: []\n")
    with pytest.raises(ValueError):
        load_plan(bad)
```

**Run all tests:**

```bash
pytest
```

- ✅ *Worked when:* everything passes (29 simulator + 7 harness = **36 passed**).

---

## Part D — Docker sanity + push

The Docker image installs `requirements.txt`, so PyYAML will be picked up
automatically.

```bash
docker build -t modem-harness . && docker run --rm modem-harness
git add .
git commit -m "Day 7: YAML test-plan schema + validating loader + example plans"
git push
```

- ✅ **DAY 7 IS DONE when:** CI is green with 36 tests, and `load_plan` parses the
  example plans and rejects malformed ones.

---

## If something breaks

- **`ModuleNotFoundError: No module named 'yaml'`:** PyYAML isn't installed — run
  `pip install -r requirements.txt` in your venv (the package is imported as
  `yaml` even though it's installed as `PyYAML`).
- **`ModuleNotFoundError: No module named 'harness'`:** make sure
  `harness/__init__.py` exists and you're running `pytest` from the repo root.
- **A YAML file "won't parse" / weird values:** YAML is indentation-sensitive (use
  spaces, not tabs) and cares about quoting. Keep the AT commands quoted (`"AT"`),
  especially regex strings.
- **`test_regex_field_is_parsed` can't find the case:** the case `name` in the YAML
  must exactly match the string in the test (`signal quality format`).
- **CI red, local green:** confirm `requirements.txt`, the `harness/` files,
  `testplans/`, and `test_harness.py` were all committed.

---

## Progress log (updated as we go)

*(Fill in as you work through today.)*

---

*When CI is green with 36 tests, Day 7 is done — and we pause for a REVIEW SESSION
of everything so far (simulator + harness foundation) before Day 8 wires the driver
that actually runs these plans against the modem through a Transport interface.*
