# Day 5 Checklist — The registration state machine

**Goal for today:** make the simulator model how a real modem gets onto a network.
You'll add a **finite state machine** for registration (SIM not ready → not
registered → registered / roaming), a small **parser** that understands the write
and read forms of AT commands, and the four commands that drive and report
registration: `AT+CFUN`, `AT+CGATT`, `AT+COPS`, `AT+CREG`.

By end of day you can walk the modem through a realistic power-on sequence:
check SIM → turn the radio on → see it register → attach packet service → read the
operator — and watch it *refuse* illegal steps (like attaching before it's
registered).

**Time:** ~4 hours (the biggest simulator day). **Prereqs:** Day 4 done, CI green.

> Code blocks start at the left margin — copy-paste directly.

---

## Background knowledge (read before you build — this is the important part)

### 1. What a finite state machine (FSM) is

An FSM is a model with a fixed set of **states**, where the system is in exactly
**one** state at a time, and **transitions** move it between states in response to
**events**. A traffic light (green → yellow → red → green) is the classic example.

A modem's network registration is naturally an FSM: it's either *not registered*,
*searching*, *registered at home*, *roaming*, or *denied* — never two at once. We
model it that way because:
- **It mirrors reality** — this is literally how the cellular standard describes it.
- **It's testable** — you can assert "after CFUN=1, state is REGISTERED."
- **It prevents illegal states** — you can only ever be in one defined state, and
  you can reject transitions that shouldn't happen (attaching before registering).

Being able to say "I modeled registration as a finite state machine" — and explain
why — is a strong signal in a systems/test interview.

### 2. The real registration sequence (what we're modeling)

Here's what actually happens when a cellular modem powers on, and the AT command
that drives or observes each step:

1. **Is the SIM ready?** (`AT+CPIN?`) — no ready SIM, no network. (Day 4.)
2. **Turn the radio on.** (`AT+CFUN=1`) — CFUN = "phone functionality". `1` = full
   (radio on), `0` = minimum (radio off, like airplane mode).
3. **Find and register on a network.** The modem searches, then registers — either
   on its **home** network or, away from home, **roaming** on a partner network.
4. **Check registration status.** (`AT+CREG?`) — the modem reports a status code.
5. **Attach to packet (data) service.** (`AT+CGATT=1`) — voice registration and
   data attach are separate steps; you can be registered but not attached.
6. **See which operator you're on.** (`AT+COPS?`) — returns the network name.

### 3. The four registration commands

- **`AT+CFUN`** — *set functionality.* Write `=1` (radio on) / `=0` (radio off).
  This is the main driver of our state machine. Read `?` returns the current level.
- **`AT+CREG`** — *network registration status.* Read `?` returns
  `+CREG: <n>,<stat>`. The **stat** code is the FSM state, encoded as a number
  (table below). Write `=n` sets how verbose the reporting is.
- **`AT+CGATT`** — *packet-service attach.* Write `=1` attach / `=0` detach; read
  `?` returns 0/1. Attaching requires being registered first.
- **`AT+COPS`** — *operator selection.* Read `?` returns the current operator name;
  write `=0` requests automatic selection.

**The CREG status codes** (memorize these — they come up in real conformance work):

| Code | Meaning | Our state |
|---|---|---|
| 0 | Not registered, not searching | `NOT_REGISTERED` / `SIM_NOT_READY` |
| 1 | Registered, home network | `REGISTERED` |
| 2 | Not registered, searching | `SEARCHING` |
| 3 | Registration denied | `DENIED` |
| 4 | Unknown | *(fallback)* |
| 5 | Registered, roaming | `ROAMING` |

(We reach `NOT_REGISTERED`, `REGISTERED`, and `SIM_NOT_READY` on the normal path
today. `SEARCHING`, `DENIED`, and `ROAMING` exist in the enum and get exercised by
fault injection on Day 12 — a modem stuck searching or getting denied is exactly
the kind of fault the harness must catch.)

### 4. Parsing AT command forms (the small parser we add today)

Until now every command was an exact string. Now we have `AT+CFUN=1`, `AT+CFUN=0`,
`AT+CFUN?`, `AT+CFUN=?` — same command, different **forms**. So we add a parser
that splits an extended command into `(verb, form, value)`:

- `AT+CFUN=1`  → verb `CFUN`, form `write`, value `1`
- `AT+CREG?`   → verb `CREG`, form `read`
- `AT+CFUN=?`  → verb `CFUN`, form `test`
- `AT+CSQ`     → verb `CSQ`,  form `execute`

Each handler then decides what to do based on the form. This is a natural evolution
of the dispatch table, not a rewrite of the idea.

### 5. Derived state vs stored state (a subtle but important design choice)

We do **not** store the registration state as an independent variable that we set
by hand in ten places (easy to get out of sync). Instead we store the *inputs* —
`sim_ready` and `functionality` — and **derive** the registration state from them
in one function, `_recompute_registration()`. Whenever an input changes, we
recompute. This gives us a **single source of truth** and makes illegal or
inconsistent states impossible. "Derive, don't duplicate" is a principle worth
being able to name.

### 6. Guard conditions (the conformance-testing mindset)

Some transitions are illegal: you can't attach to packet service (`AT+CGATT=1`) if
you're not registered. A real modem returns `ERROR`. We enforce that with a
**guard** — an `if` that rejects the command when the precondition isn't met.
Modeling and testing illegal transitions is *literally what conformance testing
is*, so this is the most on-topic code in the whole simulator for your target
roles.

### The state machine, drawn

```
   SIM_NOT_READY
       |  AT+CPIN=<pin>   (enter PIN -> sim_ready = True)
       v
   NOT_REGISTERED  <----- AT+CFUN=0 (radio off) -----  REGISTERED
       |                                                   ^   |
       |  AT+CFUN=1 (radio on, SIM ready)  -----------------+ |
       |                                                       |
       |                             AT+CGATT=1 (needs REGISTERED)
       |                                     attaches packet service
       v                                                       v
   (stays NOT_REGISTERED                              REGISTERED + attached
    if SIM not ready)                                 ----(away from home)---> ROAMING

   Inputs that drive the machine:  sim_ready (AT+CPIN)  and  functionality (AT+CFUN)
   reg_state is DERIVED from those two by _recompute_registration().

   SEARCHING and DENIED exist in the enum and are reached via fault injection (Day 12).
```

---

## Part A — Rewrite `simulator/commands.py`

This is a big edit: we add the state enum, the derive function, the parser, and the
four new handlers, and we change every extended handler to the
`(state, form, value)` signature. Replace the whole file with the version below.
`server.py` still needs no changes — `handle_command(line, state)` is unchanged.

```python
"""
commands.py — Translates AT commands into modem responses.

The "brain" of the simulator, kept separate from networking (server.py).

Structure:
  - ModemState : the modem's memory (echo, SIM, radio functionality, attach).
  - RegState   : the finite-state-machine states for network registration.
  - _recompute_registration() : DERIVES the registration state from its inputs,
    so there is a single source of truth (no hand-set, out-of-sync state).
  - _parse_extended() : splits an AT+ command into (verb, form, value).
  - handlers   : one small function per command.
  - BASIC_COMMANDS / EXTENDED_COMMANDS : the dispatch tables.

Command coverage:
  Day 3: AT, ATE0/ATE1.
  Day 4: identity (CGMI, CGMM, CIMI, CSQ) + SIM status (CPIN).
  Day 5 (now): registration state machine (CFUN, CREG, CGATT, COPS).
"""

from dataclasses import dataclass, field
from enum import Enum


class RegState(Enum):
    """The finite set of network-registration states. The modem is always in
    exactly one of these. The comment shows the AT+CREG status code each maps to.
    """
    SIM_NOT_READY = 0    # no usable SIM            -> CREG 0
    NOT_REGISTERED = 0   # SIM ok, radio off/idle   -> CREG 0
    SEARCHING = 2        # looking for a network    -> CREG 2 (fault-injection)
    REGISTERED = 1       # registered, home network -> CREG 1
    ROAMING = 5          # registered, roaming      -> CREG 5
    DENIED = 3           # registration denied      -> CREG 3 (fault-injection)


# Map each state to the numeric code AT+CREG reports. (Two states share code 0.)
CREG_STATUS_CODE = {
    RegState.SIM_NOT_READY: 0,
    RegState.NOT_REGISTERED: 0,
    RegState.SEARCHING: 2,
    RegState.REGISTERED: 1,
    RegState.ROAMING: 5,
    RegState.DENIED: 3,
}


@dataclass
class ModemState:
    """Everything the simulated modem remembers between commands.

    We store the *inputs* to registration (sim_ready, functionality) and DERIVE
    reg_state from them, rather than setting reg_state by hand everywhere.
    """
    echo: bool = True          # command echo on/off (ATE1/ATE0)
    sim_ready: bool = True      # is the SIM unlocked/usable? (AT+CPIN)
    functionality: int = 1      # AT+CFUN: 1=full (radio on), 0=minimum (radio off)
    creg_mode: int = 0          # AT+CREG reporting verbosity (the <n> value)
    attached: bool = False      # AT+CGATT packet-service attach state
    reg_state: RegState = field(default=RegState.NOT_REGISTERED)

    def __post_init__(self):
        # Derive the initial registration state from the initial inputs.
        _recompute_registration(self)


def _recompute_registration(state: ModemState) -> None:
    """DERIVE reg_state from its inputs. Called whenever an input changes.

    Rules (normal path):
      - SIM not ready            -> SIM_NOT_READY
      - SIM ready but radio off  -> NOT_REGISTERED
      - SIM ready and radio on   -> REGISTERED (home network)
    If we end up not registered, we cannot stay attached to packet service.
    """
    if not state.sim_ready:
        state.reg_state = RegState.SIM_NOT_READY
    elif state.functionality == 0:
        state.reg_state = RegState.NOT_REGISTERED
    else:
        state.reg_state = RegState.REGISTERED

    # Guard: packet attach can't survive loss of registration.
    if state.reg_state not in (RegState.REGISTERED, RegState.ROAMING):
        state.attached = False


# The literal a modem sends on failure / unknown command.
ERROR = "ERROR"


def _ok(info: str | None = None) -> str:
    """Body of a successful response: optional info line + blank line + OK.
    server.py adds the outer CRLF framing.
    """
    if info is None:
        return "OK"
    return f"{info}\r\n\r\nOK"


def _parse_extended(cmd: str):
    """Split an 'AT+...' command into (verb, form, value).

    forms: 'test' (=?), 'write' (=value), 'read' (?), 'execute' (bare).
    Returns None if `cmd` is not an extended (AT+) command.
    """
    if not cmd.startswith("AT+"):
        return None
    body = cmd[3:]                       # drop "AT+", e.g. "CFUN=1"
    if body.endswith("=?"):
        return (body[:-2], "test", None)
    if "=" in body:
        verb, value = body.split("=", 1)
        return (verb, "write", value)
    if body.endswith("?"):
        return (body[:-1], "read", None)
    return (body, "execute", None)


# --- Basic command handlers (take only state) ------------------------------

def _cmd_at(state: ModemState) -> str:
    return _ok()


def _cmd_ate0(state: ModemState) -> str:
    state.echo = False
    return _ok()


def _cmd_ate1(state: ModemState) -> str:
    state.echo = True
    return _ok()


# --- Extended command handlers (take state, form, value) -------------------

def _cmd_cgmi(state, form, value):
    return _ok("SimCorp")                # manufacturer


def _cmd_cgmm(state, form, value):
    return _ok("SC-LTE-100")             # model


def _cmd_cimi(state, form, value):
    # IMSI (subscriber identity). Requires a ready SIM.
    if not state.sim_ready:
        return ERROR
    return _ok("310150123456789")


def _cmd_csq(state, form, value):
    return _ok("+CSQ: 20,99")            # signal quality


def _cmd_cpin(state, form, value):
    if form == "read":
        status = "READY" if state.sim_ready else "SIM PIN"
        return _ok(f"+CPIN: {status}")
    if form == "write":
        # Entering any PIN unlocks the simulated SIM, then re-derive state.
        state.sim_ready = True
        _recompute_registration(state)
        return _ok()
    return ERROR


def _cmd_cfun(state, form, value):
    # Phone functionality: the main driver of the registration state machine.
    if form == "read":
        return _ok(f"+CFUN: {state.functionality}")
    if form == "write":
        if value in ("0", "1"):
            state.functionality = int(value)
            _recompute_registration(state)   # radio change re-derives registration
            return _ok()
        return ERROR
    if form == "test":
        return _ok("+CFUN: (0,1)")
    return ERROR


def _cmd_creg(state, form, value):
    # Network registration status reporting.
    if form == "read":
        stat = CREG_STATUS_CODE.get(state.reg_state, 4)
        return _ok(f"+CREG: {state.creg_mode},{stat}")
    if form == "write":
        if value.isdigit():
            state.creg_mode = int(value)
            return _ok()
        return ERROR
    if form == "test":
        return _ok("+CREG: (0-2)")
    return ERROR


def _cmd_cgatt(state, form, value):
    # Packet-service attach/detach.
    if form == "read":
        return _ok(f"+CGATT: {1 if state.attached else 0}")
    if form == "write":
        if value == "1":
            # GUARD: can only attach if registered. Illegal otherwise -> ERROR.
            if state.reg_state in (RegState.REGISTERED, RegState.ROAMING):
                state.attached = True
                return _ok()
            return ERROR
        if value == "0":
            state.attached = False
            return _ok()
        return ERROR
    return ERROR


def _cmd_cops(state, form, value):
    # Operator selection / identification.
    if form == "read":
        if state.reg_state in (RegState.REGISTERED, RegState.ROAMING):
            # +COPS: <mode>,<format>,<operator>,<AcT>  (AcT 7 = LTE/E-UTRAN)
            return _ok('+COPS: 0,0,"SimCorp Telecom",7')
        return _ok("+COPS: 0")           # not registered: no operator
    if form == "write":
        return _ok()                     # accept automatic/manual requests
    if form == "test":
        return _ok('+COPS: (2,"SimCorp Telecom","SimCorp","310150",7)')
    return ERROR


# --- Dispatch tables --------------------------------------------------------

BASIC_COMMANDS = {
    "AT": _cmd_at,
    "ATE0": _cmd_ate0,
    "ATE1": _cmd_ate1,
}

# Keyed by the verb WITHOUT the "AT+" prefix.
EXTENDED_COMMANDS = {
    "CGMI": _cmd_cgmi,
    "CGMM": _cmd_cgmm,
    "CIMI": _cmd_cimi,
    "CSQ": _cmd_csq,
    "CPIN": _cmd_cpin,
    "CFUN": _cmd_cfun,
    "CREG": _cmd_creg,
    "CGATT": _cmd_cgatt,
    "COPS": _cmd_cops,
}


def handle_command(line: str, state: ModemState) -> str:
    """Return the response body for one AT command line.

    Basic commands (AT, ATE0/1) are matched exactly. Extended (AT+...) commands
    are parsed into (verb, form, value) and routed to their handler. Commands are
    case-insensitive. Unknown commands return ERROR, like real hardware.
    """
    cmd = line.upper().strip()

    if cmd in BASIC_COMMANDS:
        return BASIC_COMMANDS[cmd](state)

    parsed = _parse_extended(cmd)
    if parsed is None:
        return ERROR                     # not a basic or extended command
    verb, form, value = parsed

    handler = EXTENDED_COMMANDS.get(verb)
    if handler is None:
        return ERROR                     # unknown extended command
    return handler(state, form, value)
```

- [ ] `simulator/commands.py` replaced with the version above.
- [ ] `server.py` confirmed unchanged.

---

## Part B — Walk the modem through a power-on sequence by hand

**1. Start the simulator** (port 5050) and connect with `nc localhost 5050` in a
second terminal. Send `ATE0` first for clean output, then walk this sequence:

```
ATE0            -> OK
AT+CPIN?        -> +CPIN: READY        (SIM is ready by default)
AT+CREG?        -> +CREG: 0,1          (already registered: SIM ready + radio on)
AT+CFUN=0       -> OK                  (turn the radio OFF)
AT+CREG?        -> +CREG: 0,0          (now NOT registered)
AT+CGATT=1      -> ERROR               (GUARD: can't attach while not registered)
AT+CFUN=1       -> OK                  (radio back ON)
AT+CREG?        -> +CREG: 0,1          (registered again)
AT+CGATT=1      -> OK                  (now attach succeeds)
AT+CGATT?       -> +CGATT: 1
AT+COPS?        -> +COPS: 0,0,"SimCorp Telecom",7
```

- ✅ *Worked when:* the sequence behaves exactly as above — especially the
  `ERROR` on `AT+CGATT=1` while the radio is off. That single line is your
  conformance-testing story: the modem correctly *refuses an illegal transition*.
- Bonus: try the SIM-lock path in a fresh connection is harder to trigger over
  `nc` (SIM is ready by default); the unit tests below cover it instead.

---

## Part C — Add automated tests

Append to `test_simulator.py`. Note the new import for `RegState` isn't needed —
we assert on the CREG text output instead, which is what a real harness sees.

```python
# --- Day 5: registration state machine -------------------------------------

def test_default_is_registered_home():
    # SIM ready + radio on by default -> registered on home network (CREG stat 1).
    state = ModemState()
    assert "+CREG: 0,1" in handle_command("AT+CREG?", state)


def test_radio_off_deregisters():
    state = ModemState()
    assert handle_command("AT+CFUN=0", state) == "OK"
    assert "+CREG: 0,0" in handle_command("AT+CREG?", state)


def test_radio_on_registers_again():
    state = ModemState()
    handle_command("AT+CFUN=0", state)
    handle_command("AT+CFUN=1", state)
    assert "+CREG: 0,1" in handle_command("AT+CREG?", state)


def test_sim_not_ready_is_not_registered():
    state = ModemState(sim_ready=False)
    assert "+CPIN: SIM PIN" in handle_command("AT+CPIN?", state)
    assert "+CREG: 0,0" in handle_command("AT+CREG?", state)


def test_entering_pin_unlocks_and_registers():
    state = ModemState(sim_ready=False)
    assert handle_command("AT+CPIN=1234", state) == "OK"
    assert "+CREG: 0,1" in handle_command("AT+CREG?", state)


def test_cannot_attach_when_not_registered():
    # GUARD: attaching before registration is an illegal transition -> ERROR.
    state = ModemState()
    handle_command("AT+CFUN=0", state)               # radio off -> not registered
    assert handle_command("AT+CGATT=1", state) == "ERROR"


def test_can_attach_when_registered():
    state = ModemState()                             # registered by default
    assert handle_command("AT+CGATT=1", state) == "OK"
    assert "+CGATT: 1" in handle_command("AT+CGATT?", state)


def test_losing_registration_clears_attach():
    state = ModemState()
    handle_command("AT+CGATT=1", state)              # attached
    handle_command("AT+CFUN=0", state)               # radio off -> deregister
    assert "+CGATT: 0" in handle_command("AT+CGATT?", state)


def test_cops_shows_operator_when_registered():
    state = ModemState()
    assert "SimCorp Telecom" in handle_command("AT+COPS?", state)


def test_cops_shows_no_operator_when_not_registered():
    state = ModemState()
    handle_command("AT+CFUN=0", state)
    assert handle_command("AT+COPS?", state) == "+COPS: 0\r\n\r\nOK"


def test_cfun_read_reports_level():
    state = ModemState()
    assert "+CFUN: 1" in handle_command("AT+CFUN?", state)
```

**Run them:**

```bash
pytest
```

- ✅ *Worked when:* all pass (12 from before + 11 new = **23 passed**).

---

## Part D — (Optional) Docker sanity check

```bash
docker build -t modem-harness . && docker run --rm modem-harness
```

- ✅ *Worked when:* `23 passed` inside the container.

---

## Part E — Save your work and watch CI

```bash
git add .
git commit -m "Day 5: registration state machine (CFUN/CREG/CGATT/COPS) + AT command parser"
git push
```

- ✅ **DAY 5 IS DONE when:** CI is green with 23 passing tests and the manual
  power-on sequence behaves correctly (including the ERROR guard).

---

## If something breaks

- **`AT+CFUN=1` returns `ERROR`:** the parser splits on the first `=`; make sure
  you didn't add spaces (`AT+CFUN =1`). The value must be exactly `0` or `1`.
- **`AT+CGATT=1` unexpectedly returns `OK` when you expected `ERROR`:** you're
  probably still registered — send `AT+CFUN=0` first to drop registration, then
  try the attach.
- **`AT+CREG?` shows the wrong code:** trace it back to the inputs — `sim_ready`
  and `functionality` — since the state is derived from them by
  `_recompute_registration`. Print the state in the handler if needed.
- **A test about `+COPS: 0` fails on exact match:** remember `_ok()` appends
  `\r\n\r\nOK`, so the full body is `+COPS: 0\r\n\r\nOK`. Match a substring if the
  exact form trips you up.
- **CI red, local green:** confirm `commands.py` and `test_simulator.py` were both
  committed.

---

## Progress log (updated as we go)

*(Fill in as you work through today.)*

---

*When CI is green with 23 tests, Day 5 is done — and the simulator is
feature-complete enough to be worth testing seriously. Day 6 adds the last
commands (AT+CGDCONT for PDP context, AT+CMEE for error verbosity), hardens the
server against malformed input, and then FREEZES the simulator so we can pivot to
building the harness.*
