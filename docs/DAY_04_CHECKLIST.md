# Day 4 Checklist — Command dispatch + identity commands

**Goal for today:** two things. (1) Refactor the growing `if/elif` chain in
`commands.py` into a clean **dispatch table** (a dict that maps a command to a
handler function). (2) Add the modem's **identity commands** — `AT+CGMI`,
`AT+CGMM`, `AT+CIMI`, `AT+CSQ` — and the SIM ready-state check `AT+CPIN?`.

By end of day the simulator answers real informational queries ("who made you?",
"what's your signal?", "is the SIM ready?") in the format a real modem uses.

**Time:** ~3–4 hours. **Prereqs:** Day 3 done (simulator runs, CI green).

> Code blocks start at the left margin — copy-paste directly.

---

## Background knowledge (read before you build)

### 1. The dispatch-table pattern (today's big refactor)

Right now `handle_command` is a chain of `if cmd == "AT": ... elif cmd == "ATE0":
...`. That's fine for 3 commands. By the end of the project we'll have ~14, plus
argument parsing. An if/elif wall gets unreadable and every new command means
editing one giant function.

The fix is a **dispatch table**: a dictionary mapping each command string to a
small handler function.

```python
COMMANDS = {
    "AT": _cmd_at,
    "AT+CSQ": _cmd_csq,
    # ...
}
handler = COMMANDS.get(cmd)      # look up in O(1), no long scan
```

Why this is better, and worth saying in an interview:
- **Readable:** each command's logic is its own named function.
- **Extensible:** adding a command = write a function + add one dict entry. You
  never touch the others (this is the "open/closed principle" — open to extension,
  closed to modification).
- **Fast:** dict lookup is constant-time; an if/elif chain checks each branch in
  order.
- **Testable:** you can test each handler in isolation.

This pattern has names you can drop: *table-driven methods*, or a lightweight
*Command pattern*.

### 2. Basic vs extended AT commands, and the four forms

- **Basic commands** are short and prefix-free: `AT`, `ATE0`, `ATH` (hang up).
- **Extended commands** start with `AT+` and a keyword: `AT+CSQ`, `AT+CPIN`. These
  come from the public 3GPP TS 27.007 standard.

Extended commands have up to four *forms*, distinguished by their suffix:

| Form | Suffix | Meaning | Example |
|---|---|---|---|
| Test | `=?` | "What values do you support?" | `AT+CFUN=?` |
| Read | `?` | "What's your current value?" | `AT+CPIN?` |
| Write/Set | `=<value>` | "Set this value." | `AT+CFUN=1` |
| Execute | *(none)* | "Do the action / return the info." | `AT+CIMI` |

Today we use the **read** form (`AT+CPIN?` — asking the SIM's status) and the
**execute** form (`AT+CGMI`, `AT+CSQ`, etc. — just return the info). We'll add
write forms on Day 5 (e.g. `AT+CFUN=0`).

### 3. What each command actually means (cellular background)

- **`AT+CGMI` — manufacturer identification.** Returns the maker's name. On real
  hardware, e.g. "Quectel". Ours returns an invented vendor (public command, fake
  device — no confidentiality issue).
- **`AT+CGMM` — model identification.** Returns the model string, e.g.
  "SC-LTE-100" for us.
- **`AT+CIMI` — request IMSI.** The **IMSI** (International Mobile Subscriber
  Identity) is the unique ID of the *subscriber*, stored on the SIM. Structure:
  **MCC** (3 digits, mobile country code) + **MNC** (2–3 digits, mobile network
  code) + **MSIN** (the subscriber number). It requires the SIM to be ready —
  which is why we gate it on `sim_ready`.
- **`AT+CSQ` — signal quality.** Returns `+CSQ: <rssi>,<ber>`. **RSSI** (received
  signal strength) is 0–31 (higher = stronger; 99 = unknown). **BER** (bit error
  rate) is 0–7 (99 = unknown). So `+CSQ: 20,99` means "decent signal, error rate
  unknown."
- **`AT+CPIN?` — SIM PIN status.** `+CPIN: READY` means the SIM is unlocked and
  usable. `+CPIN: SIM PIN` means it's waiting for a PIN. This is the gate that
  Day 5's registration logic depends on — no ready SIM, no network.

### 4. The response format (information response + result code)

A real modem answers a data query with two parts: an **information response**
line carrying the data, then a final **result code** (`OK`). With echo off, the
raw bytes for `AT+CSQ` look like:

```
\r\n+CSQ: 20,99\r\n     <- information response (the data)
\r\nOK\r\n              <- final result code
```

We model this with a small `_ok(info)` helper that formats "info line, blank line,
OK". `server.py` already wraps the outer `\r\n`, so we don't touch it today —
another payoff of the plumbing/brain split.

---

## Part A — Refactor `commands.py` to a dispatch table + add commands

Replace the entire contents of `simulator/commands.py` with the version below.
It keeps the same public function (`handle_command(line, state)`), so `server.py`
needs **no changes** — you're improving the internals behind a stable interface,
which is itself a good thing to be able to say you did.

```python
"""
commands.py — Translates AT commands into modem responses.

The "brain" of the simulator, kept separate from networking (server.py) so it can
be unit-tested with no sockets.

Design: commands are dispatched through a TABLE (the COMMANDS dict) that maps a
command string to a small handler function. Adding a command means writing a
handler and adding one dict entry — no edits to the others.

Command coverage:
  Day 3: AT, ATE0/ATE1.
  Day 4 (now): identity commands (CGMI, CGMM, CIMI, CSQ) + SIM status (CPIN?).
  Day 5: registration state machine (CREG, CGATT, COPS, CFUN=...).
"""

from dataclasses import dataclass


@dataclass
class ModemState:
    """Everything the simulated modem remembers between commands.

    Fields grow over time; adding one here never breaks existing callers.
    """
    echo: bool = True         # Real modems power on with echo ENABLED (ATE1).
    sim_ready: bool = True    # Is the SIM unlocked and usable? (drives AT+CPIN?)


# The literal a modem sends when a command fails or is unknown.
ERROR = "ERROR"


def _ok(info: str | None = None) -> str:
    """Build the body of a SUCCESSFUL response.

    - No info  -> just "OK" (for commands like AT, ATE0).
    - With info -> an information response line, a blank line, then "OK",
      matching how real modems return data followed by a final result code.
    server.py adds the outer CRLF framing, so we don't add it here.
    """
    if info is None:
        return "OK"
    return f"{info}\r\n\r\nOK"


# --- Individual command handlers -------------------------------------------
# Each handler takes the ModemState (so it can read/modify modem memory) and
# returns the response BODY as a string.

def _cmd_at(state: ModemState) -> str:
    # "AT" is an "are you there?" ping. Always succeeds.
    return _ok()


def _cmd_ate0(state: ModemState) -> str:
    state.echo = False          # turn command echo OFF
    return _ok()


def _cmd_ate1(state: ModemState) -> str:
    state.echo = True           # turn command echo ON
    return _ok()


def _cmd_cgmi(state: ModemState) -> str:
    # Manufacturer identification. Invented value (public command, fake device).
    return _ok("SimCorp")


def _cmd_cgmm(state: ModemState) -> str:
    # Model identification.
    return _ok("SC-LTE-100")


def _cmd_cimi(state: ModemState) -> str:
    # IMSI = subscriber identity stored on the SIM. Needs a ready SIM, so we
    # gate it: no ready SIM -> ERROR, just like real hardware.
    # Test IMSI: MCC=310 (USA), MNC=150, then the subscriber number.
    if not state.sim_ready:
        return ERROR
    return _ok("310150123456789")


def _cmd_csq(state: ModemState) -> str:
    # Signal quality: +CSQ: <rssi 0-31, 99=unknown>,<ber 0-7, 99=unknown>.
    return _ok("+CSQ: 20,99")


def _cmd_cpin_read(state: ModemState) -> str:
    # SIM PIN status. READY = unlocked/usable; SIM PIN = waiting for a PIN.
    status = "READY" if state.sim_ready else "SIM PIN"
    return _ok(f"+CPIN: {status}")


# --- Dispatch table: command string -> handler function --------------------
# To add a command: write a handler above, then add one line here.
COMMANDS = {
    "AT": _cmd_at,
    "ATE0": _cmd_ate0,
    "ATE1": _cmd_ate1,
    "AT+CGMI": _cmd_cgmi,
    "AT+CGMM": _cmd_cgmm,
    "AT+CIMI": _cmd_cimi,
    "AT+CSQ": _cmd_csq,
    "AT+CPIN?": _cmd_cpin_read,
}


def handle_command(line: str, state: ModemState) -> str:
    """Return the response body for one AT command line.

    Looks the command up in the dispatch table and calls its handler. Unknown
    commands return ERROR, exactly as a real modem would. Commands are
    case-insensitive, so we normalize to uppercase first.
    """
    cmd = line.upper().strip()
    handler = COMMANDS.get(cmd)
    if handler is None:
        return ERROR
    return handler(state)
```

- [ ] `simulator/commands.py` replaced with the dispatch-table version above.
- [ ] Confirm `server.py` is unchanged (it still just calls
      `handle_command(line, state)`).

---

## Part B — Run it and poke it by hand

**1. Start the simulator** (remember: port 5050 now):

```bash
python -m simulator.server
```

**2. In a second terminal, connect and try the new commands:**

```bash
nc localhost 5050
```

Send these (press Enter after each). Tip: send `ATE0` first so replies are clean.

- `ATE0`      → `OK`
- `AT+CGMI`   → `SimCorp` then `OK`
- `AT+CGMM`   → `SC-LTE-100` then `OK`
- `AT+CIMI`   → `310150123456789` then `OK`
- `AT+CSQ`    → `+CSQ: 20,99` then `OK`
- `AT+CPIN?`  → `+CPIN: READY` then `OK`
- `AT+BOGUS`  → `ERROR`

- ✅ *Worked when:* each returns the value above, and the first terminal logs
  every command with its latency. Quit with `Ctrl+C` in both terminals.

---

## Part C — Add automated tests

Append these tests to `test_simulator.py` (below your existing Day 3 tests). They
cover the new commands AND the SIM-gating behavior.

```python
# --- Day 4: identity commands + SIM status ---------------------------------

def test_cgmi_returns_manufacturer():
    state = ModemState()
    body = handle_command("AT+CGMI", state)
    assert "SimCorp" in body
    assert body.endswith("OK")


def test_cgmm_returns_model():
    state = ModemState()
    assert "SC-LTE-100" in handle_command("AT+CGMM", state)


def test_cimi_returns_imsi_when_sim_ready():
    state = ModemState(sim_ready=True)
    body = handle_command("AT+CIMI", state)
    assert "310150123456789" in body


def test_cimi_errors_when_sim_not_ready():
    state = ModemState(sim_ready=False)
    assert handle_command("AT+CIMI", state) == "ERROR"


def test_csq_reports_signal_quality():
    state = ModemState()
    assert "+CSQ:" in handle_command("AT+CSQ", state)


def test_cpin_reports_ready_when_sim_ready():
    state = ModemState(sim_ready=True)
    assert "+CPIN: READY" in handle_command("AT+CPIN?", state)


def test_cpin_reports_locked_when_sim_not_ready():
    state = ModemState(sim_ready=False)
    assert "+CPIN: SIM PIN" in handle_command("AT+CPIN?", state)
```

**Run them:**

```bash
pytest
```

- ✅ *Worked when:* all tests pass (5 from Day 3 + 7 new = **12 passed**).

---

## Part D — (Optional) Docker sanity check

```bash
docker build -t modem-harness . && docker run --rm modem-harness
```

- ✅ *Worked when:* `12 passed` inside the container.

---

## Part E — Save your work and watch CI

```bash
git add .
git commit -m "Day 4: dispatch table + identity commands (CGMI/CGMM/CIMI/CSQ) + CPIN? SIM status"
git push
```

- ✅ **DAY 4 IS DONE when:** CI is green with 12 passing tests and the simulator
  answers all the identity commands correctly.

---

## If something breaks

- **A new command returns `ERROR` unexpectedly:** the dict key must match the
  uppercased command EXACTLY, including the `?` on `AT+CPIN?`. Check for typos in
  the `COMMANDS` table.
- **`AT+CIMI` returns `ERROR`:** that's correct if `sim_ready=False`. Over `nc`,
  the default state has `sim_ready=True`, so it should return the IMSI — if not,
  check the handler's `if not state.sim_ready` logic.
- **Tests can't find `ModemState`:** make sure the import line at the top of
  `test_simulator.py` is `from simulator.commands import ModemState,
  handle_command`.
- **CI red, local green:** confirm the edited `commands.py` and `test_simulator.py`
  were both committed (`git status`).

---

## Progress log (updated as we go)

- ✅ **DAY 4 COMPLETE.** Refactored `commands.py` to a dispatch table; added
  identity commands (CGMI, CGMM, CIMI, CSQ) and SIM status (CPIN?). `server.py`
  unchanged. 12 tests pass locally and in CI (green). `ModemState` gained
  `sim_ready`, gating AT+CIMI — the seed for Day 5's registration logic.

---

*When CI is green with 12 tests, Day 4 is done. Day 5 is the big one: the
registration state machine — modeling how a modem moves from "SIM not ready" to
"searching" to "registered," driven by AT+CFUN, AT+CGATT, AT+COPS, and reported by
AT+CREG.*
