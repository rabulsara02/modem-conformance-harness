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