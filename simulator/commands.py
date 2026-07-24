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
    