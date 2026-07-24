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

# --- Day 4: identity commands + SIM status ---------------------------------

def test_cgmi_returns_manufacturer():
    state = ModemState()
    body = handle_command("AT+CGMI", state)
    assert "SimCorp" in body
    assert body.endswith("OK")


def test_cgmm_returns_model():
    state = ModemState()
    assert "SC-LTE-100" in handle_command("AT+CGMM", state)


def test_cimi_returns_imsi_when_sim_ready():
    state = ModemState(sim_ready=True)
    body = handle_command("AT+CIMI", state)
    assert "310150123456789" in body


def test_cimi_errors_when_sim_not_ready():
    state = ModemState(sim_ready=False)
    assert handle_command("AT+CIMI", state) == "ERROR"


def test_csq_reports_signal_quality():
    state = ModemState()
    assert "+CSQ:" in handle_command("AT+CSQ", state)


def test_cpin_reports_ready_when_sim_ready():
    state = ModemState(sim_ready=True)
    assert "+CPIN: READY" in handle_command("AT+CPIN?", state)


def test_cpin_reports_locked_when_sim_not_ready():
    state = ModemState(sim_ready=False)
    assert "+CPIN: SIM PIN" in handle_command("AT+CPIN?", state)