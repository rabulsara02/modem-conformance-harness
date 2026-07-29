"""
selfcheck.py — Measure the fault CLASSIFIER's accuracy against KNOWN faults.

For each scenario we inject a fault ourselves, so we know the true category (the
"ground truth"). We run it, classify the outcome, and compare. Accuracy =
correct / total. This is the headline metric: how reliably the harness tells device
faults, timeouts, and harness faults apart.

Run against a live simulator:  python -m harness.selfcheck
"""

import argparse
from dataclasses import dataclass

from harness.testplan import TestCase
from harness.transport import TcpTransport
from harness.runner import run_case, CaseResult
from harness.classifier import classify, FaultCategory


@dataclass
class Scenario:
    name: str
    fault: str                 # AT+FAULT mode to set first ("none" = healthy)
    send: str
    expect: str
    expected: FaultCategory    # the true label (ground truth)
    break_transport: bool = False   # if True, aim at a dead port (a harness fault)


SCENARIOS = [
    Scenario("healthy",       "none",       "AT",       "OK",    FaultCategory.PASS),
    Scenario("lying modem",   "wrongstate", "AT+BOGUS", "ERROR", FaultCategory.DEVICE_FAULT),
    Scenario("garbled reply", "malformed",  "AT",       "OK",    FaultCategory.DEVICE_FAULT),
    Scenario("dropped conn",  "dropout",    "AT",       "OK",    FaultCategory.DEVICE_FAULT),
    Scenario("too slow",      "delay",      "AT",       "OK",    FaultCategory.TIMEOUT),
    Scenario("cant connect",  "none",       "AT",       "OK",    FaultCategory.HARNESS_FAULT,
             break_transport=True),
]


def run_scenario(sc: Scenario, host: str, port: int) -> FaultCategory:
    # For the harness-fault scenario, aim at a dead port so connecting fails on OUR side.
    target_port = 1 if sc.break_transport else port
    transport = TcpTransport(host, target_port, timeout=0.5)
    try:
        transport.open()
    except Exception as e:
        # Couldn't even connect -> our side.
        result = CaseResult(sc.name, False, sc.send, "",
                            harness_error=f"{type(e).__name__}: {e}")
        return classify(result)
    try:
        transport.send("ATE0")
        if sc.fault != "none":
            transport.send(f"AT+FAULT={sc.fault}")
        case = TestCase(name=sc.name, send=sc.send, expect=sc.expect, timeout_ms=500)
        result = run_case(case, transport)
    finally:
        transport.close()
    return classify(result)


def run_selfcheck(host: str, port: int):
    """Run all scenarios; return (accuracy_pct, rows) where each row is
    (name, expected, got, correct)."""
    rows = []
    for sc in SCENARIOS:
        got = run_scenario(sc, host, port)
        rows.append((sc.name, sc.expected.value, got.value, got == sc.expected))
    correct = sum(1 for r in rows if r[3])
    accuracy = correct / len(rows) * 100 if rows else 0.0
    return accuracy, rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure fault-classification accuracy.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args(argv)

    accuracy, rows = run_selfcheck(args.host, args.port)
    print("\n=== Fault classification self-check ===")
    for name, expected, got, ok in rows:
        print(f"  [{'OK' if ok else 'XX'}] {name:14s} expected={expected:13s} got={got}")
    correct = sum(1 for r in rows if r[3])
    print(f"classification accuracy: {accuracy:.0f}% ({correct}/{len(rows)})")
    return 0 if accuracy == 100 else 1


if __name__ == "__main__":
    raise SystemExit(main())