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