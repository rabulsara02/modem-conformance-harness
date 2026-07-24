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