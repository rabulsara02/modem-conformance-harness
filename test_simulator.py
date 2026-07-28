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

    # --- Day 5: registration state machine -------------------------------------

def test_default_is_registered_home():
    # SIM ready + radio on by default -> registered on home network (CREG stat 1).
    state = ModemState()
    assert "+CREG: 0,1" in handle_command("AT+CREG?", state)


def test_radio_off_deregisters():
    state = ModemState()
    assert handle_command("AT+CFUN=0", state) == "OK"
    assert "+CREG: 0,0" in handle_command("AT+CREG?", state)


def test_radio_on_registers_again():
    state = ModemState()
    handle_command("AT+CFUN=0", state)
    handle_command("AT+CFUN=1", state)
    assert "+CREG: 0,1" in handle_command("AT+CREG?", state)


def test_sim_not_ready_is_not_registered():
    state = ModemState(sim_ready=False)
    assert "+CPIN: SIM PIN" in handle_command("AT+CPIN?", state)
    assert "+CREG: 0,0" in handle_command("AT+CREG?", state)


def test_entering_pin_unlocks_and_registers():
    state = ModemState(sim_ready=False)
    assert handle_command("AT+CPIN=1234", state) == "OK"
    assert "+CREG: 0,1" in handle_command("AT+CREG?", state)


def test_cannot_attach_when_not_registered():
    # GUARD: attaching before registration is an illegal transition -> ERROR.
    state = ModemState()
    handle_command("AT+CFUN=0", state)               # radio off -> not registered
    assert handle_command("AT+CGATT=1", state) == "ERROR"


def test_can_attach_when_registered():
    state = ModemState()                             # registered by default
    assert handle_command("AT+CGATT=1", state) == "OK"
    assert "+CGATT: 1" in handle_command("AT+CGATT?", state)


def test_losing_registration_clears_attach():
    state = ModemState()
    handle_command("AT+CGATT=1", state)              # attached
    handle_command("AT+CFUN=0", state)               # radio off -> deregister
    assert "+CGATT: 0" in handle_command("AT+CGATT?", state)


def test_cops_shows_operator_when_registered():
    state = ModemState()
    assert "SimCorp Telecom" in handle_command("AT+COPS?", state)


def test_cops_shows_no_operator_when_not_registered():
    state = ModemState()
    handle_command("AT+CFUN=0", state)
    assert handle_command("AT+COPS?", state) == "+COPS: 0\r\n\r\nOK"


def test_cfun_read_reports_level():
    state = ModemState()
    assert "+CFUN: 1" in handle_command("AT+CFUN?", state)

# --- Day 6: PDP context, CMEE error verbosity, and robustness --------------

def test_define_and_read_pdp_context():
    state = ModemState()
    assert handle_command('AT+CGDCONT=1,"IP","internet"', state) == "OK"
    body = handle_command("AT+CGDCONT?", state)
    assert '+CGDCONT: 1,"IP","internet"' in body


def test_pdp_context_rejects_bad_cid():
    state = ModemState()
    assert handle_command('AT+CGDCONT=99,"IP","x"', state) == "ERROR"


def test_cmee_verbose_changes_error_wording():
    state = ModemState()
    assert handle_command("AT+BOGUS", state) == "ERROR"        # mode 0
    handle_command("AT+CMEE=2", state)
    assert handle_command("AT+BOGUS", state) == "+CME ERROR: unknown"


def test_cmee_numeric_error():
    state = ModemState()
    handle_command("AT+CMEE=1", state)
    assert handle_command("AT+BOGUS", state) == "+CME ERROR: 100"


def test_cmee_read_reports_mode():
    state = ModemState()
    handle_command("AT+CMEE=2", state)
    assert "+CMEE: 2" in handle_command("AT+CMEE?", state)


def test_malformed_input_never_crashes():
    # None of these should raise; each returns a clean error string.
    state = ModemState()
    for junk in ["", "   ", "AT+", "AT+CFUN=", "###", "AT+CGDCONT=", "random text"]:
        result = handle_command(junk, state)
        assert isinstance(result, str)        # got a string back, no exception
        assert result in ("ERROR", "OK") or result.startswith("+")


def test_fault_command_sets_mode():
    state = ModemState()
    assert handle_command("AT+FAULT=delay", state) == "OK"
    assert state.fault_mode == "delay"


def test_fault_command_rejects_unknown_mode():
    state = ModemState()
    assert handle_command("AT+FAULT=bogus", state) == "ERROR"