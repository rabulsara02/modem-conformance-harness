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
from simulator.faults import apply_fault

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("simulator")

HOST = "0.0.0.0"  # Listen on all interfaces so other containers can reach us.
PORT = 5050


class ATHandler(socketserver.StreamRequestHandler):
    """Handles one client connection for its entire lifetime.

    A single client may send many commands over one connection, so we loop,
    reading one line at a time, until the client disconnects.
    """

    def handle(self):
        # Each connection gets its OWN modem state, keeping parallel tests isolated.
        state = ModemState()
        client = self.client_address[0]
        log.info("client connected: %s", client)

        try:
            for raw in self.rfile:
                start = time.monotonic()

                line = raw.decode(errors="replace").strip()
                if not line:
                    continue  # ignore blank lines

                # Capture echo AND fault mode BEFORE handling the command, so the
                # command that *sets* a fault (or echo) is itself answered faithfully;
                # only *later* commands are affected.
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
        except (ConnectionResetError, BrokenPipeError):
            # The client hung up mid-exchange (common with the delay/dropout faults
            # when a client times out and closes early). That's the client's doing,
            # not a server error — log it cleanly instead of dumping a traceback.
            log.info("client %s hung up", client)

        log.info("client disconnected: %s", client)


def main():
    with socketserver.ThreadingTCPServer((HOST, PORT), ATHandler) as server:
        log.info("modem simulator listening on %s:%d", HOST, PORT)
        server.serve_forever()


if __name__ == "__main__":
    main()