"""
test_faults.py — Prove the harness OBSERVES injected faults.

Set a fault via AT+FAULT, send a normal command, and check the response is
wrong / late / dropped. Uses the shared `modem_address` fixture from conftest.py.
"""

import pytest

from harness.transport import TcpTransport


def _connect(modem_address):
    host, port = modem_address
    t = TcpTransport(host, port, timeout=0.5)   # short timeout so 'delay' fails fast
    t.open()
    t.send("ATE0")
    return t


def test_wrongstate_makes_the_modem_lie(modem_address):
    t = _connect(modem_address)
    try:
        t.send("AT+FAULT=wrongstate")
        response = t.send("AT+BOGUS")           # should be ERROR; lie returns OK
        assert "OK" in response and "ERROR" not in response
    finally:
        t.close()


def test_malformed_returns_garbage(modem_address):
    t = _connect(modem_address)
    try:
        t.send("AT+FAULT=malformed")
        assert "GARBLED" in t.send("AT")
    finally:
        t.close()


def test_delay_causes_a_timeout(modem_address):
    t = _connect(modem_address)                 # 0.5s client timeout vs 3s server delay
    try:
        t.send("AT+FAULT=delay")
        with pytest.raises(TimeoutError):
            t.send("AT")
    finally:
        t.close()


def test_dropout_closes_the_connection(modem_address):
    t = _connect(modem_address)
    try:
        t.send("AT+FAULT=dropout")
        assert t.send("AT") == ""               # empty read = peer closed
    finally:
        t.close()