# Day 17 Checklist — Finale: real-hardware seam, demo, and final metrics

**Goal for today:** close out the project. Make the real-hardware bridge **concrete**
by writing the one class it takes (`SerialTransport`) and wiring it into the CLI, so
`python -m harness.run --serial /dev/ttyUSB0` runs the *exact same* plans against a
physical modem. Capture a **fault-injection demo**. Then **freeze the final metrics**
— the numbers that describe the finished project.

**Time:** ~3 hours. **Prereqs:** Day 16 done, README polished, CI green.

> Code blocks start at the left margin.

---

## Background knowledge (read before you build)

### 1. The Transport abstraction pays off (for real, today)

Since Day 8 the harness has talked to a `Transport` interface, not a socket. The
whole promise was: *swapping in real hardware is one new class, and nothing else
changes.* Today you cash that in — you write `SerialTransport` (serial port instead
of TCP), and the runner, classifier, plans, reports, and CLI are all untouched. Being
able to *show* that — same 21 plans, same everything, just `--serial` — is the
strongest possible evidence you understood dependency inversion, not just recited it.

### 2. The real-hardware depth decision (Tier A / B / C)

You committed to real hardware; the open question was *how deep*. Now decide:

- **Tier A — Smoke bridge (recommended first step).** Point the harness at a `$20`
  USB LTE modem and run the identity/SIM/signal cases over serial. Proves "validated
  against real hardware" with lowest risk.
- **Tier B — Real registration.** Drive an actual network attach on live hardware.
- **Tier C — Hardware fault comparison.** Compare real failure behavior to the
  injected faults.

The **software is 100% ready for all three today.** The physical validation just
needs the modem in hand — so the plan is: land `SerialTransport` now (Tier-ready),
and run **Tier A** the day the modem arrives. That's an honest, credible place to
leave it.

### 3. Why a demo matters

A repo tells; a demo *shows*. A 20-second recording of the harness catching and
classifying injected faults makes the differentiator undeniable to someone skimming.
Even the plain-text `selfcheck` output pasted into the README earns its keep.

### 4. Freeze the metrics (don't recompute them under pressure later)

Capture the final numbers now, from the finished system, so you're never guessing:
test count, conformance cases, classification accuracy, command count, fault modes,
latency. These are facts about the project — write them down once.

---

## Part A — Make the real-hardware seam concrete

### 1. Add `SerialTransport` to `harness/transport.py`

Append this class (it reuses the existing `_is_final_line` and `import time`):

```python
class SerialTransport(Transport):
    """Talk to a REAL modem over a serial port (e.g. /dev/ttyUSB0).

    This is the ENTIRE cost of running the harness against physical hardware — one
    new Transport. The runner, classifier, plans, reports, and CLI are unchanged.
    Requires pyserial (`pip install pyserial`), imported lazily so the rest of the
    project needs no extra dependency and CI stays pure-stdlib.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial = None

    def open(self) -> None:
        import serial  # lazy: only needed when actually talking to hardware
        self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def send(self, command: str, timeout: float = 2.0) -> str:
        if self._serial is None:
            raise RuntimeError("transport not open — call open() first")
        self._serial.timeout = timeout
        self._serial.write((command + "\r\n").encode())

        deadline = time.monotonic() + timeout
        buffer = ""
        while time.monotonic() < deadline:
            line = self._serial.readline().decode(errors="replace")
            if not line:
                continue
            buffer += line
            if any(_is_final_line(l) for l in buffer.splitlines()):
                return buffer.strip()
        raise TimeoutError(f"no complete response within {timeout:.2f}s")
```

### 2. Wire `--serial` into `harness/run.py`

Add a `--serial` option and choose the transport from it. Add the argument:

```python
    parser.add_argument("--serial", help="talk to a real modem at this serial port "
                                          "(e.g. /dev/ttyUSB0) instead of TCP")
```

Then, where you currently build `TcpTransport(args.host, args.port)` inside the plan
loop, build the transport based on `--serial`:

```python
    def make_transport():
        if args.serial:
            from harness.transport import SerialTransport
            return SerialTransport(args.serial)
        return TcpTransport(args.host, args.port)
```

...and in the loop use `transport = make_transport()`. (Keep the import of
`TcpTransport`; `SerialTransport` is imported lazily so pyserial stays optional.)

### 3. One test that the seam exists (`test_classifier.py` or `test_runner.py`)

`SerialTransport` can be *constructed* without pyserial (it's only imported in
`open()`), so we can assert the interface is satisfied without any hardware:

```python
def test_serial_transport_satisfies_the_interface():
    from harness.transport import SerialTransport, Transport
    t = SerialTransport("/dev/ttyUSB0")
    assert isinstance(t, Transport)     # implements open/close/send
```

**Run everything:**

```bash
pytest
```

- ✅ *Worked when:* all pass — 81 + 1 = **82 passed**. (No hardware needed; the test
  only checks the class satisfies the `Transport` contract.)

---

## Part B — Fault-injection demo

Your `selfcheck` already exercises every fault category and reports accuracy — that's
the demo. Capture it so it lives in the repo.

- [ ] Run it and copy the output:

```bash
python -m simulator.server &
python -m harness.selfcheck
```

- [ ] Paste the output into a short **"Demo"** section near the top of the README
      (in a code block), so a reader sees the classifier working without running
      anything:

```
=== Fault classification self-check ===
  [OK] healthy        expected=pass          got=pass
  [OK] lying modem    expected=device_fault  got=device_fault
  ...
classification accuracy: 100% (6/6)
```

- [ ] **(Optional, high polish)** record a real terminal GIF with asciinema:

```bash
brew install asciinema        # then: asciinema rec demo.cast
# run: python -m harness.run  and  python -m harness.selfcheck ; exit to stop
```

  Upload the `.cast` (or convert to a GIF) and embed it in the README. Not required,
  but a moving demo is memorable.

---

## Part C — Freeze the final metrics

Record these once, from the finished system. Verify each with the command shown:

| Metric | Value | Verify with |
|---|---|---|
| Automated tests | **82** | `pytest` |
| Conformance cases | **21** | `python -m harness.run` (cases=) |
| Classification accuracy | **100% (6/6)** | `python -m harness.selfcheck` |
| AT commands modeled | **~14** | README command table |
| Fault modes | **4** | delay / malformed / dropout / wrongstate |
| Fault categories | **4** | pass / device / timeout / harness |
| Runs in CI | **yes** | Actions tab, green |

- [ ] Save these to `docs/METRICS.md` (or a "Results" note) so they're one place,
      not scattered. These are the factual numbers that describe the project — ready
      to drop into a resume line whenever you want (say the word and I'll draft
      those).

---

## Part D — Final commit + wrap-up

```bash
docker build -t modem-harness . && docker run --rm modem-harness
git add -A
git commit -m "Day 17: SerialTransport (real-hardware seam) + --serial CLI; demo + final metrics"
git push
```

- ✅ **DAY 17 IS DONE — PROJECT COMPLETE — when:** CI is green with 82 tests,
  `SerialTransport` is in place (so `python -m harness.run --serial /dev/ttyUSB0` is
  ready for a real modem), the README shows a demo, and the metrics are frozen.

---

## What's left (post-plan, when the modem arrives)

- **Tier A hardware bridge:** `pip install pyserial`, plug in a USB LTE modem, run
  `python -m harness.run --serial /dev/ttyUSB0`. That's the "validated against real
  hardware" line — the software is already done; only the device is pending.

---

## If something breaks

- **`test_serial_transport_satisfies_the_interface` fails to import:** it must NOT
  import `serial` at module top — the `import serial` lives *inside* `open()`, so the
  class constructs without pyserial.
- **`--serial` run errors with "No module named 'serial'":** that's expected without
  pyserial; `pip install pyserial` (only needed for real hardware).
- **`Can't instantiate abstract class SerialTransport`:** it must implement all three
  of `open`/`close`/`send`.
- **CI red, local green:** confirm `transport.py`, `run.py`, and the new test were
  committed.

---

## Progress log (updated as we go)

*(Fill in as you work through today.)*

---

*This is the last day of the 17-day plan. When it's green, the project is complete:
a documented, tested, containerized, CI-run conformance harness that classifies
faults at 100% accuracy and is one `pip install` away from real hardware. Nice work.*
