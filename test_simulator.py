"""
test_simulator.py — Unit tests for the modem simulator's command logic.

These call handle_command() directly, with NO networking. Testing the brain
apart from the plumbing keeps tests fast and flake-free (no ports, no timing).
"""

from simulator.commands import ModemState, handle_command


def test_at_returns_ok():
    state = ModemState()
    assert handle_command("AT", state) == "OK"


def test_unknown_command_returns_error():
    state = ModemState()
    assert handle_command("AT+NOPE", state) == "ERROR"


def test_ate0_disables_echo():
    state = ModemState()
    assert state.echo is True            # modems power on with echo enabled
    assert handle_command("ATE0", state) == "OK"
    assert state.echo is False           # ATE0 turned it off


def test_ate1_enables_echo():
    state = ModemState(echo=False)
    assert handle_command("ATE1", state) == "OK"
    assert state.echo is True


def test_commands_are_case_insensitive():
    state = ModemState()
    assert handle_command("at", state) == "OK"