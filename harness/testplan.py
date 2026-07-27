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

    name         : human label for reports.
    send         : the AT command to send.
    expect       : substring the response must CONTAIN (optional).
    expect_regex : regex the response must MATCH (optional).
                   At least one of expect / expect_regex is required.
    timeout_ms   : how long to wait for a response before failing.
    retries      : how many times to retry on failure/timeout.
    precondition : commands to send first to set up state (e.g. "AT+CFUN=0").
    """
    __test__ = False
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
    __test__ = False
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