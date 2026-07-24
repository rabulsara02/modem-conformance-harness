"""
sim_stub.py — 

Purpose: prove that one container can run a TCP server that another
container connects to. This is a STAND-IN. On Day 3 the real modem
simulator replaces it. For now it just echoes back whatever it receives
so we can confirm the two-container network works.
"""

import socketserver  # Python's built-in library for simple TCP/UDP servers.


class EchoHandler(socketserver.StreamRequestHandler):
    """Handles ONE client connection.

    socketserver creates a new instance of this class for every client
    that connects, and calls handle(). StreamRequestHandler gives us two
    convenient file-like objects:
      - self.rfile : read from the client
      - self.wfile : write back to the client
    """

    def handle(self):
        # Read one line from the client (up to the newline it sends).
        # .strip() removes the trailing newline and any whitespace.
        data = self.rfile.readline().strip()

        # Send a reply. We prefix "SIM_OK: " so it's obvious in the logs
        # that the response came from the simulator, not the harness.
        # Note the b"..." — TCP sends raw bytes, not text strings.
        self.wfile.write(b"SIM_OK: " + data + b"\n")


if __name__ == "__main__":
    # "0.0.0.0" means "listen on all network interfaces" — required so the
    # OTHER container can reach us (localhost/127.0.0.1 would only accept
    # connections from inside this same container). 5000 is the port.
    with socketserver.TCPServer(("0.0.0.0", 5000), EchoHandler) as server:
        # flush=True forces the message to appear in Docker logs immediately
        # instead of being buffered.
        print("sim_stub listening on 5000", flush=True)

        # Run forever, handling one client at a time, until we stop it.
        server.serve_forever()