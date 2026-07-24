# Day 3 Checklist — Build the real modem simulator (TCP server + AT parser)

**Goal for today:** replace the dumb echo box (`sim_stub.py`) with a real modem
simulator — a TCP server that *understands* AT commands. By end of day you can
connect to it, type `AT`, and get `OK`; type nonsense and get `ERROR`; and toggle
command echo with `ATE0` / `ATE1`.

**Time:** ~3–4 hours. **Prereqs:** Days 1–2 done (Python, Docker, CI all green).

> **Note on code blocks:** every code block below starts at the left margin so you
> can copy-paste it directly without stray leading spaces (which would break
> Python's indentation).

---

## First: three concepts you'll be able to explain after today

Read these once before you build. Being able to say them out loud is half the
point of the project.

1. **What an AT command is.** "AT" stands for *attention*. It's the tiny text
   language modems have used since the 1980s. You send a short text line like
   `AT` or `AT+CIMI`, the modem does something, and replies with a result —
   usually `OK`, `ERROR`, or some data followed by `OK`. That's the entire
   protocol we're simulating. The commands themselves are public (3GPP TS 27.007).

2. **Why a TCP server (a real modem uses a serial port).** Real modems talk over
   a serial cable (`/dev/ttyUSB0`). That's awkward to test from another program or
   another container. So we expose the *same* line-based AT interface over a
   network socket instead. Same commands, easier to reach. (When we bridge to real
   hardware on Day 17, only the transport swaps — serial instead of TCP — not the
   logic.)

3. **Why we split "plumbing" from "brain."** Networking code (accept
   connections, read/write bytes) goes in `server.py`. Command logic (what does
   `AT` mean, what do we reply) goes in `commands.py`. This separation means we
   can test the brain with fast, reliable unit tests that never open a socket —
   no ports, no timing, no flakiness. This is a deliberate, defensible design
   choice, not an accident.

**Echo, explained (you'll see it today):** Real modems power on with *echo on*
(`ATE1`) — they repeat back each command you send before answering. `ATE0` turns
that off. Test harnesses usually send `ATE0` first so replies are clean. We model
this faithfully, which is why you'll briefly see commands appear twice.

---

## Part A — Create the simulator package

We put the simulator in its own folder (a Python "package") so it stays organized
as it grows over Days 4–5.

**1. Make the package folder and files.** In your editor, create three files:

```
simulator/__init__.py     (marks the folder as a package)
simulator/commands.py
simulator/server.py
```

For `simulator/__init__.py`, one line is enough:

```python
"""simulator — a fake cellular modem that speaks AT commands over TCP."""
```

**2. Write `simulator/commands.py`** — the "brain" (command logic, no networking):

```python
"""
commands.py — Translates AT commands into modem responses.

This is the "brain" of the simulator. It is deliberately kept separate from
the networking layer (server.py) so we can unit-test command behavior WITHOUT
opening any sockets — fast and reliable.

Grows over the next few days:
  Day 3 (now): AT, ATE0/ATE1, and ERROR for anything unknown.
  Day 4: identity commands (CGMI, CGMM, CIMI, CSQ, CPIN?).
  Day 5: registration state machine (CREG, CGATT, COPS, CFUN).
"""

from dataclasses import dataclass


@dataclass
class ModemState:
    """Everything the simulated modem must remember between commands.

    Today that's just the echo setting. Using a dataclass means we can add
    fields later (SIM state, registration state) without changing the code
    that creates a ModemState.
    """
    echo: bool = True  # Real modems power on with echo ENABLED (ATE1).


def handle_command(line: str, state: ModemState) -> str:
    """Return the response BODY for one AT command line.

    - `line`  : the command text the client sent, e.g. "AT" or "ATE0".
    - `state` : the modem's memory; this function may change it (ATE0/ATE1).
    - returns : just the body ("OK" / "ERROR"). server.py adds the CRLF
                wrapping and the command echo — this function stays purely
                about "what does this command mean".

    Real modems treat commands case-insensitively, so we normalize to
    uppercase before comparing.
    """
    cmd = line.upper()

    if cmd == "AT":
        # Bare "AT" is an "are you there?" check. Always OK.
        return "OK"

    if cmd == "ATE0":
        state.echo = False   # turn command echo OFF
        return "OK"

    if cmd == "ATE1":
        state.echo = True    # turn command echo ON
        return "OK"

    # Anything we don't recognize yet: real modems reply ERROR. (Later,
    # once AT+CMEE is set, some errors become coded "+CME ERROR" replies.)
    return "ERROR"
```

**3. Write `simulator/server.py`** — the "plumbing" (networking only):

```python
"""
server.py — TCP server that makes the simulator reachable over the network.

A real modem talks over a serial port; we expose the same line-based AT
interface over TCP so other programs and containers can reach it. This file
handles ONLY networking — the command logic lives in commands.py.

Run it with:   python -m simulator.server
"""

import logging
import socketserver
import time

from simulator.commands import ModemState, handle_command

# Structured logging: every line is timestamped with a level and message.
# We log each command in and response out (with latency) so we can debug
# behavior and, later, measure performance.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("simulator")

HOST = "0.0.0.0"  # Listen on all interfaces so other containers can reach us.
PORT = 5000


class ATHandler(socketserver.StreamRequestHandler):
    """Handles one client connection for its entire lifetime.

    A single client may send many commands over one connection, so we loop,
    reading one line at a time, until the client disconnects.
    """

    def handle(self):
        # Each connection gets its OWN modem state. A real modem is one
        # device, but per-connection state keeps parallel tests isolated.
        state = ModemState()
        client = self.client_address[0]
        log.info("client connected: %s", client)

        # Iterating self.rfile yields one line per loop; it ends when the
        # client closes the connection.
        for raw in self.rfile:
            start = time.monotonic()  # start timing this command

            # Bytes -> text, and strip the trailing CR/LF and spaces.
            line = raw.decode(errors="replace").strip()
            if not line:
                continue  # ignore blank lines

            # IMPORTANT: capture the echo setting BEFORE handling the
            # command. Real modems echo the characters as they arrive, so
            # even "ATE0" itself gets echoed — only *later* commands don't.
            echo_before = state.echo

            # Ask the brain what to reply; it may also update `state`.
            body = handle_command(line, state)

            # Build the reply the way a real modem formats it:
            #   [echo of the command]\r\n \r\n<body>\r\n
            reply = ""
            if echo_before:
                reply += line + "\r\n"
            reply += "\r\n" + body + "\r\n"

            self.wfile.write(reply.encode())

            latency_ms = (time.monotonic() - start) * 1000
            log.info("cmd=%r -> %r (%.2f ms)", line, body, latency_ms)

        log.info("client disconnected: %s", client)


def main():
    # ThreadingTCPServer runs each client in its own thread so multiple
    # connections don't block each other.
    with socketserver.ThreadingTCPServer((HOST, PORT), ATHandler) as server:
        log.info("modem simulator listening on %s:%d", HOST, PORT)
        server.serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] Files `simulator/__init__.py`, `simulator/commands.py`, and
      `simulator/server.py` created with the code above.

---

## Part B — Run it and poke it by hand

**4. Start the simulator** (from the repo root, with your venv active):

```bash
python -m simulator.server
```

- ✅ *Worked when:* you see `... modem simulator listening on 0.0.0.0:5000`.
- Leave this running. Open a SECOND terminal tab for the next step.

**5. Connect and send commands** (in the second terminal):

```bash
nc localhost 5000
```

Then type these, pressing Enter after each:

- `AT`   → you should see `OK`. (Echo is on by default, so you may see `AT`
  appear twice: once as you type it, once echoed by the modem — that's correct.)
- `ATE0` → `OK`, and now echo is off, so replies get cleaner.
- `AT`   → `OK` (no echoed command this time).
- `HELLO` → `ERROR` (unknown command).
- `at`   → `OK` (commands are case-insensitive).

- ✅ *Worked when:* all of the above behave as described. Watch the FIRST
  terminal — every command logs a line like `cmd='AT' -> 'OK' (0.03 ms)`.
- Quit `nc` with `Ctrl+C`. Stop the server with `Ctrl+C` in its terminal.

---

## Part C — Write automated tests (so CI proves it works)

We test the "brain" directly — no sockets — which keeps tests fast and reliable.

**6. Create `test_simulator.py`** in the repo root (same level as `simulator/`):

```python
"""
test_simulator.py — Unit tests for the modem simulator's command logic.

These call handle_command() directly, with NO networking. Testing the brain
apart from the plumbing keeps tests fast and flake-free (no ports, no timing).
"""

from simulator.commands import ModemState, handle_command


def test_at_returns_ok():
    state = ModemState()
    assert handle_command("AT", state) == "OK"


def test_unknown_command_returns_error():
    state = ModemState()
    assert handle_command("AT+NOPE", state) == "ERROR"


def test_ate0_disables_echo():
    state = ModemState()
    assert state.echo is True            # modems power on with echo enabled
    assert handle_command("ATE0", state) == "OK"
    assert state.echo is False           # ATE0 turned it off


def test_ate1_enables_echo():
    state = ModemState(echo=False)
    assert handle_command("ATE1", state) == "OK"
    assert state.echo is True


def test_commands_are_case_insensitive():
    state = ModemState()
    assert handle_command("at", state) == "OK"
```

**7. Run the tests locally:**

```bash
pytest
```

- ✅ *Worked when:* you see `5 passed` (plus the old hello test until you remove
  it in the next step).

---

## Part D — Clean up the Day 1 scaffolding

`hello.py` / `test_hello.py` were throwaways to prove CI worked. Now that real
code and real tests exist, remove them so the repo reflects the actual project.

**8. Delete the scaffolding and re-run tests:**

```bash
rm hello.py test_hello.py
pytest
```

- ✅ *Worked when:* `5 passed` and no errors about a missing `hello` module.
- *Leave `sim_stub.py` and `harness_stub.py` for now* — they still back the
  Day 2 compose demo. We retire them on Day 7 when the real harness arrives.

**9. (Optional sanity check) Build the Docker image** to confirm nothing broke in
the container:

```bash
docker build -t modem-harness . && docker run --rm modem-harness
```

- ✅ *Worked when:* `5 passed` inside the container too.

---

## Part E — Save your work and watch CI

**10. Commit and push:**

```bash
git add .
git commit -m "Day 3: real modem simulator - TCP server + AT/ATE parser + tests"
git push
```

**11. Check the Actions tab** on GitHub for the green checkmark.

- ✅ **DAY 3 IS DONE when:** CI is green with the new tests, and you can connect
  to the running simulator and get `OK` / `ERROR` correctly.

---

## If something breaks

- **`ModuleNotFoundError: No module named 'simulator'`** when running the server:
  you ran `python simulator/server.py` instead of `python -m simulator.server`.
  Use the `-m` form from the repo root — it makes Python treat `simulator` as a
  package so the `from simulator.commands import ...` line works.
- **`nc: command not found`:** install it (`brew install netcat`) or use this
  one-off Python test instead:

  ```bash
  python -c "import socket; s=socket.create_connection(('localhost',5000)); s.sendall(b'AT\n'); print(s.recv(1024))"
  ```

- **Server says "Address already in use":** a previous run is still holding port
  5000. Ctrl+C the old terminal, or `lsof -i :5000` to find the process, then
  retry.
- **pytest can't import `simulator`:** make sure `test_simulator.py` is at the
  repo root (same folder as the `simulator/` directory) and that
  `simulator/__init__.py` exists.
- **CI red but local green:** almost always the missing `simulator/__init__.py`
  (not committed) — check `git status` before pushing.

---

## Progress log (updated as we go)

- **Part A done.** `simulator/` package created: `__init__.py`, `commands.py`
  (the brain), `server.py` (the plumbing).
- **Port change:** hit `Errno 48: Address already in use` on port 5000 —
  macOS **AirPlay Receiver** owns it. Diagnosed with `lsof -i :5000`, then moved
  the simulator to **PORT = 5050**. *Standardize on 5050 everywhere going forward*
  (Compose gets aligned on Day 7).
- **Part B done.** Server runs (`listening on 0.0.0.0:5050`); manual `nc` test on
  5050 passed: `AT`→`OK`, `ATE0` cleaned echo, `HELLO`→`ERROR`, lowercase `at`→`OK`.
  Latency logged per command.
- **Next:** Part C — write `test_simulator.py`, then Part D cleanup and Part E push.

---

*When CI is green and the simulator answers AT/ATE/ERROR correctly, Day 3 is done.
Day 4 extends the brain with identity commands (CGMI, CGMM, CIMI, CSQ) and the
SIM ready-state check AT+CPIN?.*
