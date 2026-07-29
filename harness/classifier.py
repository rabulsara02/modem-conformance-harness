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