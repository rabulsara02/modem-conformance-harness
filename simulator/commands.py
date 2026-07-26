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