"""
test_runner.py — Unit tests for the runner's retry + timeout logic.

We inject a FAKE transport (a test double) programmed to fail/time out on cue, so
we can test retry behavior deterministically — no sockets, no simulator. This is
only possible because the runner depends on the Transport INTERFACE, not on a
concrete socket. That's dependency injection paying off.
"""

from harness.transport import Transport
from harness.runner import run_case
from harness.testplan import TestCase


class FakeTransport(Transport):
    """A programmable Transport for tests.

    `responses` is consumed one per send() of the command under test:
      - a str is returned as the response,
      - the TimeoutError class is raised to simulate a timeout.
    When the list is empty (e.g. for preconditions), send() just returns "OK".
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.sent = []

    def open(self):
        pass

    def close(self):
        pass

    def send(self, command, timeout=2.0):
        self.sent.append(command)
        if not self._responses:
            return "OK"
        item = self._responses.pop(0)
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item("simulated timeout")
        return item


def _case(**kw):
    base = dict(name="t", send="AT", expect="OK")
    base.update(kw)
    return TestCase(**base)


def test_passes_first_try():
    result = run_case(_case(), FakeTransport(["OK"]), backoff_base=0)
    assert result.passed
    assert result.attempts == 1


def test_retries_then_succeeds():
    result = run_case(_case(retries=1), FakeTransport(["ERROR", "OK"]), backoff_base=0)
    assert result.passed
    assert result.attempts == 2          # failed once, passed on the retry


def test_exhausts_retries_and_fails():
    result = run_case(_case(retries=1), FakeTransport(["ERROR", "ERROR"]), backoff_base=0)
    assert not result.passed
    assert result.attempts == 2


def test_timeout_is_retried_then_succeeds():
    result = run_case(_case(retries=1), FakeTransport([TimeoutError, "OK"]), backoff_base=0)
    assert result.passed
    assert result.attempts == 2


def test_timeout_exhausted_marks_timed_out():
    result = run_case(_case(retries=1), FakeTransport([TimeoutError, TimeoutError]), backoff_base=0)
    assert not result.passed
    assert result.timed_out

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