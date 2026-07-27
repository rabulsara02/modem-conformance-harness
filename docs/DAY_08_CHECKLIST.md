# Day 8 Checklist — Transport interface + the test driver

**Goal for today:** make the YAML plans actually *run*. You'll build (1) a
**Transport interface** — an abstraction the driver talks to instead of a raw
socket, so a real modem can drop in later — with a `TcpTransport` for the
simulator; (2) a small **runner** that executes one test case (preconditions →
send → check); and (3) an **integration test** that starts a live simulator and
runs every YAML case through the transport, one pytest result per case.

**Time:** ~4 hours (the most important harness day). **Prereqs:** Day 7 done, 36
tests, CI green.

> Code blocks start at the left margin. No new dependencies — all standard library.

---

## Background knowledge (read before you build)

### 1. Programming to an interface (the key idea)

Right now nothing talks to the simulator except `nc` and the tests. The driver
needs to *send commands and read responses*. The naive way is to call socket code
directly in the driver. We won't — because then swapping in a real modem (serial
port, not TCP) would mean rewriting the driver.

Instead we define an **interface** — an abstract `Transport` with three methods
(`open`, `close`, `send`) — and the driver only ever uses *that*. TCP is one
implementation; a serial implementation comes on Day 17. The driver can't tell the
difference. This is **dependency inversion** / **"program to an interface, not an
implementation."** In architecture terms it's a **port-and-adapter** (hexagonal)
design: the driver defines the port, each transport is an adapter.

This is the single most defensible design decision in the whole project. When an
interviewer asks "how would you test against real hardware?", the answer is
"I already can — I'd write one new Transport; nothing else changes."

### 2. Abstract base classes (`ABC`, `@abstractmethod`)

Python's `abc` module lets you declare a class that *cannot be instantiated on its
own* and lists methods every subclass **must** implement. If a subclass forgets
one, Python raises an error. It's how we make "every Transport must have
send/open/close" a rule the language enforces, not just a hope.

### 3. pytest fixtures (setup / teardown)

A **fixture** is reusable setup a test depends on. A `yield` fixture runs setup,
hands the value to the test, and runs teardown after. Ours starts the simulator in
a background thread, yields its address, and shuts it down afterward — so tests
never depend on you manually starting a server.

### 4. pytest parametrization (one test, many cases)

`@pytest.mark.parametrize` runs the *same* test function once per input, each as a
separate reported result. We generate the inputs from the YAML plans — so every
YAML case becomes its own pass/fail line. This is where **data-driven testing**
pays off: add a YAML case, get a new test automatically.

### 5. Unit vs integration tests (you'll now have both)

- `test_simulator.py` / `test_harness.py` = **unit** tests (logic in isolation, no
  sockets).
- Today's `test_integration.py` = **integration** tests: a real server, a real
  socket, the real transport — the pieces working *together*.

### 6. Reading a full response from a stream (framing, again)

A modem reply can be several lines and always ends with a **final result code**
(`OK`, `ERROR`, or `+CME ERROR: ...`). Over TCP there are no message boundaries, so
`send()` must **read until it sees a final result code** (or times out). Same
"you impose the framing" lesson as Day 3, now on the reading side.

We also send **`ATE0` first** to turn echo off, so responses aren't cluttered with
the command echoed back.

### 7. Ephemeral ports (port 0) and test isolation

The fixture binds to port **0**, which tells the OS "pick any free port." That
sidesteps the 5050/AirPlay conflict entirely and lets tests run in parallel. And
because the simulator keeps state **per connection** (a Day 3 decision), each test
opening its own connection gets a **fresh modem** — clean isolation for free.

---

## Part A — The Transport interface + TCP implementation

Create `harness/transport.py`:

```python
"""
transport.py — How the harness TALKS to a modem.

The harness must not care whether the modem is the TCP simulator or a real device
on a serial port. So we define a small Transport INTERFACE and program the driver
against it — not against sockets directly. Today: TcpTransport (for the simulator).
Day 17: a SerialTransport for real hardware drops in with ZERO driver changes.
That swap-ability is the entire reason this abstraction exists.
"""

import socket
from abc import ABC, abstractmethod


class Transport(ABC):
    """Abstract interface for sending AT commands and reading responses.

    ABC = Abstract Base Class: this can't be instantiated directly, and any
    concrete transport MUST implement all three methods below (Python enforces it).
    """

    @abstractmethod
    def open(self) -> None:
        """Establish the connection to the modem."""

    @abstractmethod
    def close(self) -> None:
        """Tear the connection down."""

    @abstractmethod
    def send(self, command: str) -> str:
        """Send one AT command and return the modem's full response text."""


# Lines that mark the END of a modem response.
def _is_final_line(line: str) -> bool:
    s = line.strip()
    return s in ("OK", "ERROR") or s.startswith("+CME ERROR") or s.startswith("+CMS ERROR")


def _read_response(sock: socket.socket) -> str:
    """Read from the socket until a final result code appears (or it times out).

    TCP has no message boundaries, so we accumulate bytes and stop once we see a
    line like OK / ERROR / +CME ERROR. On timeout we return what we have.
    """
    buffer = ""
    while True:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            break
        if not chunk:                          # peer closed the connection
            break
        buffer += chunk.decode(errors="replace")
        if any(_is_final_line(line) for line in buffer.splitlines()):
            break
    return buffer.strip()


class TcpTransport(Transport):
    """A Transport that talks to the modem SIMULATOR over TCP."""

    def __init__(self, host: str, port: int, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None

    def open(self) -> None:
        # create_connection resolves the address and connects, with a timeout.
        self._sock = socket.create_connection((self.host, self.port), self.timeout)
        self._sock.settimeout(self.timeout)    # also bound each recv() by timeout

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def send(self, command: str) -> str:
        if self._sock is None:
            raise RuntimeError("transport not open — call open() first")
        # The simulator frames on newline, so terminate the command with CRLF.
        self._sock.sendall((command + "\r\n").encode())
        return _read_response(self._sock)
```

- [ ] `harness/transport.py` created.

---

## Part B — The runner (execute one case, return a result)

Create `harness/runner.py`:

```python
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
```

- [ ] `harness/runner.py` created.

---

## Part C — Integration test: run every YAML case against a live simulator

Create `test_integration.py` at the repo root:

```python
"""
test_integration.py — Run the YAML test plans against a LIVE simulator over TCP,
through the Transport interface.

These are INTEGRATION tests (real server + real socket + real transport), unlike
the unit tests in test_simulator.py / test_harness.py. A fixture starts the
simulator in a background thread on an ephemeral port; each YAML case becomes its
own parametrized pytest result.
"""

import socketserver
import threading
from pathlib import Path

import pytest

from simulator.server import ATHandler
from harness.testplan import load_plan
from harness.transport import TcpTransport
from harness.runner import run_case

TESTPLANS = Path(__file__).parent / "testplans"


def _all_cases():
    """Collect every case from every YAML plan, with a readable test id."""
    params = []
    for plan_path in sorted(TESTPLANS.glob("*.yaml")):
        plan = load_plan(plan_path)
        for case in plan.cases:
            params.append(pytest.param(case, id=f"{plan_path.stem}:{case.name}"))
    return params


@pytest.fixture(scope="module")
def modem_address():
    """Start the simulator in a background thread on an OS-chosen free port.

    Port 0 = 'pick any free port', which avoids conflicts. Teardown (after yield)
    shuts the server down cleanly.
    """
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), ATHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address            # (host, port)
    finally:
        server.shutdown()                      # stop the serve_forever() loop
        server.server_close()                  # release the listening socket


@pytest.mark.parametrize("case", _all_cases())
def test_plan_case(case, modem_address):
    host, port = modem_address
    transport = TcpTransport(host, port)
    transport.open()                           # each test = its own connection = fresh modem state
    try:
        transport.send("ATE0")                 # disable echo for clean responses
        result = run_case(case, transport)
    finally:
        transport.close()
    assert result.passed, (
        f"{result.name}: {result.reason}\nsent={result.sent!r} response={result.response!r}"
    )
```

**Run everything:**

```bash
pytest
```

- ✅ *Worked when:* all pass — 36 from before + 9 parametrized integration cases
  (5 identity + 4 registration) = **45 passed**. Try `pytest -v` to see each YAML
  case listed by name.

---

## Part D — See a failure on purpose (build intuition)

Temporarily break one expectation to watch the harness catch it — this is the whole
point of the tool.

- [ ] In `testplans/identity.yaml`, change the manufacturer case's `expect` from
      `"SimCorp"` to `"WrongCorp"`. Run `pytest -v`.
- [ ] You should see exactly that one case FAIL, with a message showing the sent
      command and the actual response. Everything else stays green.
- [ ] Change it back to `"SimCorp"` and confirm `45 passed` again.

This proves the harness reports *per-case* pass/fail with a useful diagnostic —
the foundation for the reporting and fault-classification work later.

---

## Part E — Clean up the Day 2 stubs and wire compose to the real simulator

The Day 2 `sim_stub.py` / `harness_stub.py` are now superseded by the real
transport and runner. Retire them, and point Docker Compose at the actual
simulator so `docker compose up` launches something real.

- [ ] Delete the stubs:

```bash
rm sim_stub.py harness_stub.py
```

- [ ] Replace `docker-compose.yml` with:

```yaml
# docker-compose.yml — run the real modem simulator in a container.
# `docker compose up` builds the image and starts the simulator, with its port
# published to the host so you can connect with `nc localhost 5050`.
services:
  simulator:
    build: .
    command: python -m simulator.server
    ports:
      - "5050:5050"
```

- [ ] Confirm it still comes up:

```bash
docker compose up --build
# in another terminal: nc localhost 5050  -> ATE0, AT, etc.  Then Ctrl+C, docker compose down
```

---

## Part F — Docker sanity + push

```bash
docker build -t modem-harness . && docker run --rm modem-harness
git add -A
git commit -m "Day 8: Transport interface + TcpTransport + runner + integration tests; retire stubs; compose runs real simulator"
git push
```

- ✅ **DAY 8 IS DONE when:** CI is green with 45 tests, every YAML case runs against
  the live simulator, and `docker compose up` starts the real simulator.

---

## If something breaks

- **`Can't instantiate abstract class ... with abstract methods`:** your
  `TcpTransport` is missing one of `open`/`close`/`send`, or a name is misspelled —
  the ABC enforces all three.
- **Integration test hangs then times out:** `_read_response` never saw a final
  line. Check the command actually returns OK/ERROR, and that you sent `ATE0` (with
  echo on, the echoed line can confuse matching for some cases).
- **`ConnectionRefusedError`:** the fixture server didn't start, or you built
  `TcpTransport` with the wrong host/port — use the `(host, port)` the fixture
  yields.
- **A registration case fails:** remember each test is a fresh connection (fresh
  state: SIM ready, radio on → registered). Preconditions must set up the state the
  case needs.
- **`git add .` missed the deletions:** use `git add -A` so the removed stubs are
  staged too.
- **`AttributeError: 'ThreadingTCPServer' object has no attribute 'close'` at
  teardown:** the correct methods are `server.shutdown()` then
  `server.server_close()` — `socketserver` uses `server_close()`, not `close()`.
  (Tests still "pass" but the fixture teardown errors until you fix this.)
- **CI red, local green:** confirm `harness/transport.py`, `harness/runner.py`,
  `test_integration.py`, and the new `docker-compose.yml` were all committed.

---

## Progress log (updated as we go)

*(Fill in as you work through today.)*

---

*When CI is green with 45 tests, Day 8 is done — the harness now RUNS. Day 9 makes
it robust: per-case timeouts and retry logic (using the `timeout_ms` and `retries`
fields we already parse), plus structured logging of every command.*
