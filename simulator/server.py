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
PORT = 5050


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