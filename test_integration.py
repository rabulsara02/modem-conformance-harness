"""
test_integration.py — Run the YAML test plans against a LIVE simulator over TCP,
through the Transport interface.

These are INTEGRATION tests (real server + real socket + real transport), unlike
the unit tests in test_simulator.py / test_harness.py. A fixture starts the
simulator in a background thread on an ephemeral port; each YAML case becomes its
own parametrized pytest result.
"""


from pathlib import Path

import pytest

from simulator.server import ATHandler
from harness.testplan import load_plan
from harness.transport import TcpTransport
from harness.runner import run_case

TESTPLANS = Path(__file__).parent / "testplans"


def _all_cases():
    """Collect every case from every YAML plan, with a readable test id."""
    params = []
    for plan_path in sorted(TESTPLANS.glob("*.yaml")):
        plan = load_plan(plan_path)
        for case in plan.cases:
            params.append(pytest.param(case, id=f"{plan_path.stem}:{case.name}"))
    return params





@pytest.mark.parametrize("case", _all_cases())
def test_plan_case(case, modem_address):
    host, port = modem_address
    transport = TcpTransport(host, port)
    transport.open()                           # each test = its own connection = fresh modem state
    try:
        transport.send("ATE0")                 # disable echo for clean responses
        result = run_case(case, transport)
    finally:
        transport.close()
    assert result.passed, (
        f"{result.name}: {result.reason}\nsent={result.sent!r} response={result.response!r}"
    )