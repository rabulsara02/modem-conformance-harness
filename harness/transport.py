"""
transport.py — How the harness TALKS to a modem.

The harness must not care whether the modem is the TCP simulator or a real device
on a serial port. So we define a small Transport INTERFACE and program the driver
against it — not against sockets directly. Today: TcpTransport (for the simulator).
Day 17: a SerialTransport for real hardware drops in with ZERO driver changes.
That swap-ability is the entire reason this abstraction exists.
"""

import socket
import time
from abc import ABC, abstractmethod


class Transport(ABC):
    """Abstract interface for sending AT commands and reading responses.

    ABC = Abstract Base Class: this can't be instantiated directly, and any
    concrete transport MUST implement all three methods below (Python enforces it).
    """

    @abstractmethod
    def open(self) -> None:
        """Establish the connection to the modem."""

    @abstractmethod
    def close(self) -> None:
        """Tear the connection down."""

    @abstractmethod
    def send(self, command: str, timeout: float = 2.0) -> str:
        """Send one AT command and return the modem's full response text.
        
        Must raise TimeoutError if no complete response arrives within `timeout`.
        """


# Lines that mark the END of a modem response.
def _is_final_line(line: str) -> bool:
    s = line.strip()
    return s in ("OK", "ERROR") or s.startswith("+CME ERROR") or s.startswith("+CMS ERROR")


def _read_response(sock: socket.socket, timeout: float) -> str:
    """Read until a final result code appears, or raise TimeoutError at the deadline.

    We compute a deadline (now + timeout) and, before each read, bound the socket's
    wait by the time remaining. If the deadline passes with no complete response,
    we raise TimeoutError instead of hanging.
    """
    deadline = time.monotonic() + timeout
    buffer = ""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"no complete response within {timeout:.2f}s")
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            raise TimeoutError(f"no complete response within {timeout:.2f}s")
        if not chunk:                          # peer closed the connection
            break
        buffer += chunk.decode(errors="replace")
        if any(_is_final_line(line) for line in buffer.splitlines()):
            return buffer.strip()
    return buffer.strip()


class TcpTransport(Transport):
    """A Transport that talks to the modem SIMULATOR over TCP."""

    def __init__(self, host: str, port: int, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None

    def open(self) -> None:
        # create_connection resolves the address and connects, with a timeout.
        self._sock = socket.create_connection((self.host, self.port), self.timeout)
        self._sock.settimeout(self.timeout)    # also bound each recv() by timeout

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def send(self, command: str, timeout: float = 2.0) -> str:
        if self._sock is None:
            raise RuntimeError("transport not open — call open() first")
        # The simulator frames on newline, so terminate the command with CRLF.
        self._sock.sendall((command + "\r\n").encode())
        return _read_response(self._sock, timeout)