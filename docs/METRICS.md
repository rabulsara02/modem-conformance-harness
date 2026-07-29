# Project Metrics

Frozen facts about the finished project, each reproducible with the command shown.
Captured from the completed system (17-day build).

## Headline numbers

| Metric | Value | Verify with |
|---|---|---|
| Automated tests | **82**, all passing | `pytest` |
| Conformance test cases | **21** (100% pass) | `python -m harness.run` → `cases=21 ... pass_rate=100.0%` |
| Fault-classification accuracy | **100% (6/6)** | `python -m harness.selfcheck` |
| AT commands modeled | **14** | README command table / `simulator/commands.py` |
| Fault-injection modes | **4** (delay, malformed, dropout, wrongstate) | `simulator/faults.py` |
| Fault categories classified | **4** (pass, device, timeout, harness) | `harness/classifier.py` |
| Continuous integration | **green on every push** | GitHub Actions tab |
| Containerized | **yes** (Docker + Compose) | `docker compose up --build` |
| Real-hardware ready | **one class** (`SerialTransport`) | `python -m harness.run --serial /dev/ttyUSB0` |

## Test suite breakdown (82 total)

| Module | Kind | What it covers |
|---|---|---|
| `test_simulator.py` | unit | AT command logic + registration state machine |
| `test_harness.py` | unit | YAML test-plan loader + validation |
| `test_runner.py` | unit | timeout / retry / backoff (via a fake transport) |
| `test_report.py` | unit | metrics aggregation + JUnit/HTML generation |
| `test_classifier.py` | unit | fault classification + Transport interface |
| `test_faults.py` | integration | injected faults observed over a live socket |
| `test_integration.py` | integration | every YAML case run against a live simulator |
| `test_selfcheck.py` | integration | classifier scores 100% on known faults |

Split: fast, deterministic **unit** tests (no sockets) + **integration** tests that
start a real simulator in-process and drive it over a real socket through the
Transport interface. Every YAML case is also its own parametrized test.

## Performance note

A full conformance pass of 21 cases against the simulator completes in **~5 ms**
total — because the simulator answers instantly with zero network/serial latency.
Against a real modem over a serial port (`--serial`), the same pass would take
substantially longer; the harness records per-case latency and total duration so
that difference is measured, not guessed.

## What the numbers describe

A documented, tested, containerized, CI-run cellular-modem **conformance harness**:
a simulator with a network-registration state machine and on-demand fault injection,
and a data-driven harness that runs declarative YAML plans and classifies every
failure as a device fault, a timeout, or a harness fault — measured at 100% accuracy
across labeled fault scenarios — with JSON / JUnit / HTML reporting and a one-class
path to real hardware.

Everything is built from the **public 3GPP TS 27.007** command set; no confidential
or device-specific behavior.

*(These are the factual numbers behind the project — ready to drop into a resume
line or interview whenever needed.)*
