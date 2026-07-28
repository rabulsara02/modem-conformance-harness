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