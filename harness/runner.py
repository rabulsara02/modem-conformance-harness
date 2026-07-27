"""
runner.py — Execute a single TestCase against a Transport and report the result.

Kept transport-agnostic: it calls transport.send(), never touching sockets. That's
what lets the exact same runner drive the simulator today and real hardware later.

(Per-case timeout and retries land on Day 9; today we run each case once.)
"""

import re
from dataclasses import dataclass


@dataclass
class CaseResult:
    """The outcome of running one test case."""
    name: str
    passed: bool
    sent: str
    response: str
    reason: str = ""       # why it failed (empty if it passed)


def _check(case, response: str):
    """Return (passed, reason) by comparing the response to the case's expectation."""
    if case.expect is not None:
        if case.expect in response:
            return True, ""
        return False, f"expected substring {case.expect!r} not found"
    if case.expect_regex is not None:
        if re.search(case.expect_regex, response):
            return True, ""
        return False, f"regex {case.expect_regex!r} did not match"
    return False, "case has no expectation"     # loader prevents this, but be safe


def run_case(case, transport) -> CaseResult:
    """Send any preconditions, then the command under test, then check the reply."""
    # Preconditions set up state (e.g. AT+CFUN=0). We send and read each to keep
    # the socket in sync, but ignore their responses.
    for pre in case.precondition:
        transport.send(pre)

    response = transport.send(case.send)
    passed, reason = _check(case, response)
    return CaseResult(
        name=case.name, passed=passed, sent=case.send, response=response, reason=reason
    )