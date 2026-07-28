"""
conftest.py — Shared pytest fixtures, auto-discovered by pytest for all test files.
"""

import socketserver
import threading

import pytest

from simulator.server import ATHandler


@pytest.fixture(scope="module")
def modem_address():
    """Start the simulator in a background thread on an OS-chosen free port."""
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), ATHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()