# Day 9 Checklist — Timeouts, retries, and structured logging

**Goal for today:** make the runner robust. Wire the `timeout_ms` and `retries`
fields (parsed since Day 7) into real behavior: a case that gets no response in
time **times out cleanly** instead of hanging, and a case allowed retries is
**retried with backoff**, recording how many attempts it took. Log every attempt.

You'll also test all of this **deterministically** by injecting a *fake* modem —
which only works because you programmed against the Transport interface on Day 8.

**Time:** ~3.5 hours. **Prereqs:** Day 8 done, 45 tests, CI green.

> Code blocks start at the left margin. No new dependencies.

---

## Background knowledge (read before you build)

### 1. Timeouts — never wait forever

A test that hangs is worse than one that fails, because it blocks the whole run. So
every wait must be **bounded**: if the modem doesn't produce a complete response
within the case's `timeout_ms`, we stop waiting and record a timeout. We implement
this with a **deadline** (`now + timeout`): before each socket read we compute the
time remaining and never read past the deadline.

### 2. Retries — transient vs persistent failures

Real hardware is flaky: a command occasionally times out or gives a wrong answer
once, then works. **Retries** let a case survive a *transient* blip. But retries
cut both ways, and the nuance matters in interviews:

- Retries hide **transient** failures (good — a one-off glitch shouldn't fail a
  build).
- Retries can also **mask real bugs** if you retry blindly. That's why we *record
  the retry count* — a case that "passes on attempt 4 every time" is really a
  failing case wearing a disguise, and the metric exposes it.

Recording attempts, not just pass/fail, is exactly the kind of signal
fault-classification (Day 12) is built on.

### 3. Exponential backoff

Between retries we wait, and the wait **grows** each time (0.05s, 0.1s, 0.2s, ...) —
**exponential backoff**. Why grow it? Hammering a struggling device immediately
rarely helps; giving it increasing breathing room does. (Production systems add
random **jitter** too, so many clients don't retry in lockstep — worth a mention.)

### 4. Exceptions as control flow

When a read hits its deadline, `send()` **raises** `TimeoutError`. The runner
**catches** it and treats it as a failed attempt to retry. Using an exception here
is clean: the normal path returns a response; the exceptional path (no response)
raises. The caller decides what to do.

### 5. Test doubles / dependency injection (today's star technique)

How do you test retry logic when the real simulator never fails? You **inject a
fake**. Because the runner talks to the `Transport` *interface*, a test can hand it
a `FakeTransport` programmed to "time out twice, then succeed" — no sockets, no
simulator, fully deterministic. This is **dependency injection** enabling a **test
double**. (Terminology: a *stub* returns canned answers; a *mock* also asserts how
it was called; a *fake* is a working lightweight substitute. Ours is a fake.)

This is the concrete payoff of Day 8's abstraction, and a great interview point:
"programming to an interface let me inject a fake transport to test the retry paths
deterministically."

---

## Part A — Add timeouts to the transport

Edit `harness/transport.py`.

**1. Add `import time`** at the top (keep `import socket`):

```python
import socket
import time
from abc import ABC, abstractmethod
```

**2. Give the abstract `send` a `timeout` parameter** so every transport supports
it:

```python
    @abstractmethod
    def send(self, command: str, timeout: float = 2.0) -> str:
        """Send one AT command and return the modem's full response text.

        Must raise TimeoutError if no complete response arrives within `timeout`.
        """
```

**3. Replace `_read_response`** with a deadline-based version that raises on
timeout:

```python
def _read_response(sock: socket.socket, timeout: float) -> str:
    """Read until a final result code appears, or raise TimeoutError at the deadline.

    We compute a deadline (now + timeout) and, before each read, bound the socket's
    wait by the time remaining. If the deadline passes with no complete response,
    we raise TimeoutError instead of hanging.
    """
    deadline = time.monotonic() + timeout
    buffer = ""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"no complete response within {timeout:.2f}s")
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            raise TimeoutError(f"no complete response within {timeout:.2f}s")
        if not chunk:                          # peer closed the connection
            break
        buffer += chunk.decode(errors="replace")
        if any(_is_final_line(line) for line in buffer.splitlines()):
            return buffer.strip()
    return buffer.strip()
```

**4. Update `TcpTransport.send`** to accept and pass the timeout:

```python
    def send(self, command: str, timeout: float = 2.0) -> str:
        if self._sock is None:
            raise RuntimeError("transport not open — call open() first")
        self._sock.sendall((command + "\r\n").encode())
        return _read_response(self._sock, timeout)
```

- [ ] `transport.py` updated (import time, abstract send signature, `_read_response`,
      `TcpTransport.send`).

---

## Part B — Retry + backoff + logging in the runner

Replace the whole `harness/runner.py` with this version:

```python
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
    """Run one case: preconditions, then send-and-check with retries + backoff."""
    timeout = case.timeout_ms / 1000.0
    max_attempts = case.retries + 1

    # Preconditions set up state; best-effort (ignore their responses/timeouts).
    for pre in case.precondition:
        try:
            transport.send(pre, timeout=timeout)
        except TimeoutError:
            log.warning("case=%r precondition %r timed out", case.name, pre)

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
                return CaseResult(case.name, True, case.send, response, attempts=attempt)
        except TimeoutError as e:
            timed_out = True
            last_response, last_reason = "", str(e)
            log.warning("case=%r attempt=%d/%d TIMEOUT sent=%r",
                        case.name, attempt, max_attempts, case.send)

        # Wait before the next attempt (exponential backoff), but not after the last.
        if attempt < max_attempts:
            time.sleep(backoff_base * (2 ** (attempt - 1)))

    return CaseResult(case.name, False, case.send, last_response,
                      attempts=max_attempts, timed_out=timed_out, reason=last_reason)
```

- [ ] `runner.py` replaced.

The existing integration tests still call `run_case(case, transport)` — unchanged,
since the new parameters have defaults and the example cases have `retries: 0`.

---

## Part C — Test the retry/timeout logic with a FAKE transport

Create `test_runner.py` at the repo root:

```python
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
```

**Run everything:**

```bash
pytest
```

- ✅ *Worked when:* all pass — 45 from before + 5 runner tests = **50 passed**.

---

## Part D — (Optional) See a real timeout end-to-end

Add a temporary case to `testplans/identity.yaml` that expects something the modem
never sends, with a short timeout, and watch it fail as a timeout rather than
hang — then remove it. (The simulator always replies, so a true socket timeout is
best shown with the FakeTransport tests; this just confirms the plumbing.)

```yaml
  - name: TEMP deliberate mismatch
    send: "AT"
    expect: "NEVER_HAPPENS"
    timeout_ms: 500
    retries: 1
```

Run `pytest -v -k "TEMP"`; you'll see it fail after 2 attempts (check the message).
Delete the temporary case afterward and confirm `50 passed`.

---

## Part E — Docker sanity + push

```bash
docker build -t modem-harness . && docker run --rm modem-harness
git add -A
git commit -m "Day 9: per-case timeout + retry with backoff + structured logging; fake-transport runner tests"
git push
```

- ✅ **DAY 9 IS DONE when:** CI is green with 50 tests, retries/timeouts are honored
  per case, and the runner records attempts + timeout status.

---

## If something breaks

- **A runner test hangs:** you're probably hitting a real `time.sleep` — pass
  `backoff_base=0` in tests (the examples do) so retries don't actually wait.
- **`TypeError: send() got an unexpected keyword argument 'timeout'`:** the abstract
  `send` and/or `TcpTransport.send` still has the old signature — both need the
  `timeout` parameter, and `FakeTransport.send` must accept it too.
- **`Can't instantiate abstract class FakeTransport`:** it must implement all three
  abstract methods (`open`, `close`, `send`).
- **Timeout never triggers on real socket:** confirm `_read_response` computes a
  deadline and raises `TimeoutError` when `remaining <= 0` / on `socket.timeout`.
- **Integration tests suddenly slow:** a case with `retries` > 0 that fails will now
  actually back off between attempts — expected. Keep example plans at `retries: 0`.
- **CI red, local green:** confirm `transport.py`, `runner.py`, and `test_runner.py`
  were all committed.

---

## Progress log (updated as we go)

- ✅ **DAY 9 COMPLETE.** Added per-case timeout (deadline-based, raises
  `TimeoutError`), retry with exponential backoff, attempt/timeout recording, and
  structured logging. Tested the retry/timeout paths deterministically with an
  injected `FakeTransport`. Verified a deliberate mismatch fails after 2 attempts.
  50 tests green in CI.
- **Bug caught + fixed:** updated `_read_response` to require a timeout but the
  `TcpTransport.send` call site still passed none — a `TypeError` (signature vs call
  site disagreement). Fixed by passing `timeout` through.

---

*When CI is green with 50 tests, Day 9 is done. Day 10 adds metrics capture: every
run emits a machine-readable summary (case counts, pass/fail, durations, retry
counts) — the numbers that become your resume bullets.*
