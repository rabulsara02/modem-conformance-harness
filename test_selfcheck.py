"""
test_selfcheck.py — The classifier scores 100% on known injected faults.
"""

from harness.selfcheck import run_selfcheck


def test_classification_accuracy_is_perfect(modem_address):
    host, port = modem_address
    accuracy, rows = run_selfcheck(host, port)
    assert accuracy == 100, rows      # rows shown on failure for debugging