# Day 12 Checklist — Fault injection (the differentiator begins)

**Goal for today:** teach the simulator to **misbehave on command**. You'll add a
simulator-only hook, `AT+FAULT=<mode>`, that makes it inject real device faults —
**delay**, **malformed**, **dropout**, **wrongstate** — so the harness finally has
genuine failures to detect. This is the payload that makes the whole project not a
toy: tomorrow (Day 13) the harness learns to *classify* these faults, which is the
single most on-topic skill for validation roles.

**Time:** ~3.5 hours. **Prereqs:** Day 11 done, 66 tests, CI green.

> This is the ONE sanctioned change to the frozen simulator (guardrail: fault
> injection only). Code blocks start at the left margin.

---



## Background knowledge (read before you build)



### 1. Fault injection / chaos engineering

You cannot trust a test system you've only ever tested on the happy path. **Fault
injection** deliberately introduces failures — delays, corrupted data, dropped
connections — to prove your detector actually detects. It's the core idea behind
**chaos engineering** (Netflix's "Chaos Monkey" randomly kills production servers to
prove the system survives). Here, we inject modem faults to prove the *harness*
catches them. "I built fault injection so I could verify the harness detects real
failures, not just confirm the happy path" is a standout interview line.

### 2. The fault taxonomy (each maps to a real modem failure)


| Fault        | What the simulator does                       | Real-world analog                      |
| ------------ | --------------------------------------------- | -------------------------------------- |
| `delay`      | waits several seconds, then answers correctly | slow/overloaded firmware               |
| `malformed`  | returns garbled, non-conforming bytes         | corrupted UART/serial data             |
| `dropout`    | sends nothing and closes the connection       | modem crash / unplugged cable          |
| `wrongstate` | answers `OK` to everything, even errors       | buggy firmware that lies about success |


These aren't random — each is a failure mode real hardware actually exhibits, and
each produces a *different observable* the harness must interpret (Day 13).

### 3. Test hooks / backdoors — keep them clearly separated

`AT+FAULT` is a **test hook**: a command that exists only to control the simulator,
not part of the real AT standard. That's fine and common, but it must be *obviously*
separate from real behavior so nobody mistakes it for conformance. We name it
distinctly, document it as simulator-only, and it never appears in a conformance
plan. Knowing to isolate test hooks from production behavior is a maturity signal.

### 4. Where faults live (keeping the brain clean)

Faults are about how the *response is delivered* (late, garbled, dropped, wrong), so
we apply them at the **server boundary** (the plumbing), not inside the command
logic (the brain). `commands.py` stays a faithful model; a new `faults.py` holds the
misbehavior; `server.py` applies it to the outgoing response. The command that
*sets* the fault is answered faithfully (using the same "capture state before
handling" trick as echo), so `AT+FAULT=delay` itself returns a prompt `OK` — only
*later* commands misbehave.

### 5. `conftest.py` — shared pytest fixtures

Your simulator-server fixture currently lives in `test_integration.py`, but the new
fault tests need it too. pytest automatically loads fixtures from a file named
`conftest.py`, making them available to every test file without importing.
Moving the fixture there is the idiomatic way to share it.

### 6. This sets up fault CLASSIFICATION (the resume feature)

Today the simulator *produces* faults. Tomorrow the harness *classifies* them:
**device fault** (modem answered, but wrong/garbled), **timeout** (no answer in
time), vs **harness fault** (our own setup/bug). That three-way distinction is
exactly what validation teams screen for — and it's only possible because today we
can generate the faults on demand.

---



## Part A — Add the fault mode to the simulator's state + control command

Edit `simulator/commands.py`.

**1. Import the fault modes** (add near the top, after the existing imports):

```python
from simulator.faults import FAULT_MODES
```

**2. Add a** `fault_mode` **field to** `ModemState` (alongside the others):

```python
    pdp_contexts: dict = field(default_factory=dict)
    fault_mode: str = "none"    # simulator-only: injected-fault mode (see faults.py)
    reg_state: RegState = field(default=RegState.NOT_REGISTERED)
```

**3. Add the** `AT+FAULT` **handler** (with the other `_cmd_`* handlers):

```python
def _cmd_fault(state, form, value):
    # SIMULATOR-ONLY test hook (NOT a real AT command): choose the injected-fault
    # mode. Effect is applied to later responses by server.py via faults.apply_fault.
    if form == "read":
        return _ok(f"+FAULT: {state.fault_mode}")
    if form == "write":
        if value in FAULT_MODES:
            state.fault_mode = value
            return _ok()
        return ERROR
    return ERROR
```

**4. Register it in** `EXTENDED_COMMANDS`**:**

```python
    "CGDCONT": _cmd_cgdcont,
    "CMEE": _cmd_cmee,
    "FAULT": _cmd_fault,
```

- [ ] `commands.py` updated (import, `fault_mode` field, handler, dispatch entry).

---



## Part B — The faults module

Create `simulator/faults.py`:

```python
"""
faults.py — Deliberate misbehavior for the simulator, to test the harness.

The simulator is normally a faithful model. In a FAULT mode (set via the
simulator-only command AT+FAULT=<mode>) it corrupts its responses on purpose, so the
harness has real device faults to detect and classify. This is a TEST HOOK — not
part of the AT standard.

Each mode mimics a real modem failure:
  delay      - answers correctly but far too late (slow firmware)
  malformed  - returns garbled, non-conforming bytes (corrupted serial data)
  dropout    - sends nothing and drops the connection (crash / unplugged)
  wrongstate - answers OK to everything, even errors (firmware that lies)
"""

import time

# Every valid mode, including the "off" default. commands.py validates against this.
FAULT_MODES = {"none", "delay", "malformed", "dropout", "wrongstate"}


def apply_fault(mode: str, body: str, *, delay_s: float = 3.0):
    """Transform a normal response `body` according to the active fault `mode`.

    Returns (send_body, drop):
      - send_body: the text to actually send (possibly corrupted), or None to send
        nothing at all.
      - drop: True if the server should close the connection after this.
    """
    if mode == "delay":
        time.sleep(delay_s)                       # correct answer, but too slow
        return body, False
    if mode == "malformed":
        return "~!GARBLED!~\r\nERROR", False      # received, but non-conforming junk
    if mode == "dropout":
        return None, True                         # send nothing, drop the connection
    if mode == "wrongstate":
        return "OK", False                        # lie: claim success no matter what
    return body, False                            # "none": behave normally
```

- [ ] `simulator/faults.py` created.

---



## Part C — Apply faults in the server (the one allowed server edit)

Edit `simulator/server.py`.

**1. Import** `apply_fault` (with the other imports):

```python
from simulator.commands import ModemState, handle_command
from simulator.faults import apply_fault
```

**2. Update the body of the** `for raw in self.rfile:` **loop.** Replace everything from
`echo_before = state.echo` down to the `log.info(... latency ...)` line with:

```python
            # Capture echo AND fault mode as they were BEFORE this command, so the
            # command that *sets* a fault is still answered faithfully (like echo).
            echo_before = state.echo
            fault_before = state.fault_mode

            body = handle_command(line, state)

            # Inject the active fault into the outgoing response, if any.
            send_body, drop = apply_fault(fault_before, body)

            if send_body is not None:
                reply = ""
                if echo_before:
                    reply += line + "\r\n"
                reply += "\r\n" + send_body + "\r\n"
                self.wfile.write(reply.encode())

            latency_ms = (time.monotonic() - start) * 1000
            log.info("cmd=%r -> %r fault=%r (%.2f ms)", line, send_body, fault_before, latency_ms)

            if drop:
                log.info("fault=dropout: closing connection to %s", client)
                break
```

- [ ] `server.py` imports `apply_fault` and applies it in the loop.

---



## Part D — Watch each fault by hand

Start the simulator (`python -m simulator.server`) and connect
(`nc localhost 5050`). Send `ATE0` first, then try each mode:

```
ATE0                 -> OK
AT+FAULT=wrongstate  -> OK            (fault set; this ack is faithful)
AT+BOGUS             -> OK            (LIE: should be ERROR, modem claims success)
AT+CREG?             -> OK            (LIE: should be +CREG:...; just says OK)
AT+FAULT=none        -> OK            (back to honest)
AT+CREG?             -> +CREG: 0,1    (honest again)

AT+FAULT=malformed   -> OK
AT                   -> ~!GARBLED!~   then ERROR   (garbage, non-conforming)

AT+FAULT=delay       -> OK
AT                   -> (~3 second pause) then OK  (correct but slow)

AT+FAULT=dropout     -> OK
AT                   -> (connection closes; nc exits)
```

- ✅ *Worked when:* each mode produces its distinct misbehavior, and `AT+FAULT=none`
restores honest behavior. Notice the fault-setting command itself always answers
promptly and correctly.

---



## Part E — Move the server fixture to conftest.py + add fault tests

**1. Create** `conftest.py` at the repo root and move the `modem_address` fixture
there (cut it from `test_integration.py`):

```python
"""
conftest.py — Shared pytest fixtures, auto-discovered by pytest for all test files.
"""

import socketserver
import threading

import pytest

from simulator.server import ATHandler


@pytest.fixture(scope="module")
def modem_address():
    """Start the simulator in a background thread on an OS-chosen free port."""
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), ATHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
```

**2. In** `test_integration.py`**, delete the** `modem_address` **fixture** (and its now-unused
`socketserver`/`threading`/`ATHandler` imports). Keep everything else — the tests
still get `modem_address` automatically from `conftest.py`.

**3. Create** `test_faults.py` at the repo root:

```python
"""
test_faults.py — Prove the harness OBSERVES injected faults.

We set a fault via AT+FAULT, then send a normal command and check the response is
wrong / late / dropped. (Day 13 turns these observations into a classification.)
Uses the shared `modem_address` fixture from conftest.py.
"""

from harness.transport import TcpTransport


def _connect(modem_address):
    host, port = modem_address
    t = TcpTransport(host, port, timeout=0.5)   # short timeout so 'delay' fails fast
    t.open()
    t.send("ATE0")                              # echo off for clean responses
    return t


def test_wrongstate_makes_the_modem_lie(modem_address):
    t = _connect(modem_address)
    try:
        t.send("AT+FAULT=wrongstate")
        # AT+BOGUS should be ERROR; a lying modem returns OK instead.
        response = t.send("AT+BOGUS")
        assert "OK" in response
        assert "ERROR" not in response
    finally:
        t.close()


def test_malformed_returns_garbage(modem_address):
    t = _connect(modem_address)
    try:
        t.send("AT+FAULT=malformed")
        response = t.send("AT")                 # expected OK; get garbage instead
        assert "GARBLED" in response
    finally:
        t.close()


def test_delay_causes_a_timeout(modem_address):
    import pytest
    t = _connect(modem_address)                 # 0.5s client timeout vs 3s server delay
    try:
        t.send("AT+FAULT=delay")
        with pytest.raises(TimeoutError):
            t.send("AT")
    finally:
        t.close()


def test_dropout_closes_the_connection(modem_address):
    t = _connect(modem_address)
    try:
        t.send("AT+FAULT=dropout")
        response = t.send("AT")                 # server sends nothing and closes
        assert response == ""                   # empty read = peer closed
    finally:
        t.close()
```

**4. Add two quick unit tests** for the control command in `test_simulator.py`:

```python
# --- Day 12: fault-injection control command ---

def test_fault_command_sets_mode():
    state = ModemState()
    assert handle_command("AT+FAULT=delay", state) == "OK"
    assert state.fault_mode == "delay"


def test_fault_command_rejects_unknown_mode():
    state = ModemState()
    assert handle_command("AT+FAULT=bogus", state) == "ERROR"
```

**Run everything:**

```bash
pytest
```

- ✅ *Worked when:* all pass — 66 + 4 fault tests + 2 unit tests = **72 passed**.
(`test_delay_causes_a_timeout` takes ~0.5s; that's the timeout firing.)

---



## Part F — Docker sanity + push

```bash
docker build -t modem-harness . && docker run --rm modem-harness
git add -A
git commit -m "Day 12: fault injection (AT+FAULT: delay/malformed/dropout/wrongstate); shared conftest fixture"
git push
```

- ✅ **DAY 12 IS DONE when:** CI is green with 72 tests, and you can drive each fault
mode by hand and see the simulator misbehave.

---



## If something breaks

- `ImportError: cannot import name 'FAULT_MODES'`**:** create `simulator/faults.py`
(Part B) before editing `commands.py`, or check the module name/spelling.
- `AT+FAULT=delay` **itself hangs:** you applied the fault using the *current*
`state.fault_mode` instead of `fault_before`. Capture the mode BEFORE
`handle_command` so the control command stays faithful.
- `test_delay_causes_a_timeout` **doesn't raise:** the client timeout (0.5s) must be
shorter than the server delay (3s). Confirm `TcpTransport(..., timeout=0.5)`.
- **Fixture not found after the move:** `conftest.py` must be at the repo root (same
level as the test files) and named exactly `conftest.py`; don't import it.
- **A normal (non-fault) test broke:** make sure the server still sends normally when
`fault_before == "none"` — `apply_fault` returns `(body, False)` in that case.
- **CI red, local green:** confirm `faults.py`, the edited `commands.py`/`server.py`,
`conftest.py`, `test_faults.py`, and `test_simulator.py` were all committed
(`git add -A`).

---



## Progress log (updated as we go)

- ✅ **DAY 12 COMPLETE.** Added fault injection: `faults.py` with 4 modes, the
simulator-only `AT+FAULT` hook, and the one sanctioned `server.py` edit to apply
faults at the boundary (using `fault_before`). Moved the server fixture to
`conftest.py`. 72 tests green in Docker + CI; all 4 faults verified by hand.
- **Debugging saga (great interview material):** faults "not working" turned out to
be (1) a stale server holding the port and then (2) the `server.py` fault edits not
saved to disk. Diagnosed with `pytest` (fresh in-process server) + noticing the
live *log format* didn't match the latest code. Lesson: when behavior ≠ code,
first confirm you're running the code you think you are.

---

*When CI is green with 72 tests and every fault mode misbehaves on demand, Day 12 is
done. Day 13 is the headline: the harness learns to CLASSIFY each failure — device
fault vs timeout vs harness fault — and measures its own classification accuracy.
That's the number your resume is built around.*