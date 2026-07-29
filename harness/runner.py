"""
runner.py — Execute a TestCase against a Transport, with timeout + retry handling.

Behavior:
  - Each case uses its own timeout (timeout_ms) and retry budget (retries).
  - A failed check OR a timeout consumes one attempt; we retry up to `retries`
    extra times, waiting a little longer before each retry (exponential backoff).
  - We record how many attempts it took and whether it ended in a timeout, so a
    "passes only after N retries" case is visible, not hidden.

Stays transport-agnostic (only calls transport.send), so the same runner drives the
simulator, real hardware, or a fake transport in tests.
"""

import logging
import re
import time
from dataclasses import dataclass

log = logging.getLogger("harness")


@dataclass
class CaseResult:
    """The outcome of running one test case."""
    name: str
    passed: bool
    sent: str
    response: str
    attempts: int = 1          # how many tries it actually took
    timed_out: bool = False    # did the final attempt end in a timeout?
    duration_ms: float = 0.0      # how long the case took (seconds) (all attempts)
    harness_error: str = ""      # set when the failure is on OUR side, not the device
    reason: str = ""           # why it failed (empty if it passed)


def _check(case, response: str):
    """Return (passed, reason) comparing the response to the case's expectation."""
    if case.expect is not None:
        if case.expect in response:
            return True, ""
        return False, f"expected substring {case.expect!r} not found"
    if case.expect_regex is not None:
        if re.search(case.expect_regex, response):
            return True, ""
        return False, f"regex {case.expect_regex!r} did not match"
    return False, "case has no expectation"


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


def run_plan(plan, transport):
    """Run every case in `plan` over an already-open transport; return CaseResults.

    Sends ATE0 first so the modem doesn't echo commands back and clutter responses.
    This is the single place that knows how to run a whole plan — both the CLI and
    any future caller use it instead of re-implementing the loop.
    """
    transport.send("ATE0")
    return [run_case(case, transport) for case in plan.cases]