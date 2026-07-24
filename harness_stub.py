"""
harness_stub.py — Day 2 placeholder for the test harness.

Purpose: prove that this container can find and talk to the simulator
container over the network. STAND-IN — the real pytest harness replaces
it starting Day 7. For now it sends one command ("AT") and prints the reply.
"""

import socket  # Lower-level networking: we act as the CLIENT here.
import time


# The simulator container may take a moment to boot and start listening.
# Sleeping 2 seconds is a crude but effective way to avoid connecting
# before it's ready. (We replace this with real retry logic later.)
time.sleep(2)

# create_connection opens a TCP connection to (host, port).
# IMPORTANT: "sim" is NOT an IP address — it's the SERVICE NAME from
# docker-compose.yml. Docker's built-in DNS turns "sim" into the correct
# container address automatically. This name-based lookup is exactly how
# the real harness will find the real simulator.
with socket.create_connection(("sim", 5000)) as conn:
    # sendall guarantees the whole message goes out. b"AT\n" is raw bytes:
    # the "AT" command plus a newline so the server's readline() knows the
    # line is complete.
    conn.sendall(b"AT\n")

    # recv(1024) waits for up to 1024 bytes of reply, then we decode the
    # bytes back into a readable string and strip the trailing newline.
    reply = conn.recv(1024).decode().strip()
    print("harness got:", reply, flush=True)