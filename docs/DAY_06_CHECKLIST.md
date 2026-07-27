# Day 6 Checklist — PDP context, error verbosity, hardening, and FREEZE

**Goal for today:** finish the simulator. Add the last two commands —
`AT+CGDCONT` (define a data connection / PDP context) and `AT+CMEE` (control how
verbose error replies are) — make the server survive garbage input without
crashing, document the final command list, then **freeze the simulator**. After
today the simulator only changes for fault injection (Day 12); everything else
moves to the harness.

**Time:** ~3 hours. **Prereqs:** Day 5 done, CI green, 23 tests passing.

> Today we EDIT `commands.py` in a few specific spots rather than replace it — the
> way you'd actually work on a real codebase. Each edit says exactly where it goes.
> Code blocks start at the left margin.

---

## Background knowledge (read before you build)

### 1. PDP context (`AT+CGDCONT`) — what it is

A **PDP context** (Packet Data Protocol context) is the modem's definition of a
data connection: which **APN** (Access Point Name — the gateway to a carrier's
data network, e.g. `internet`) to use, what IP type (IPv4 / IPv6), and an ID
number (**cid**) to refer to it. Before a modem can move data, *something* has to
define a context. The command looks like:

```
AT+CGDCONT=1,"IP","internet"
```

meaning "context #1 uses IPv4 to reach the APN `internet`." Reading `AT+CGDCONT?`
lists everything you've defined. This is the last piece of a realistic data-session
setup (which sits on top of the registration you built on Day 5).

### 2. Error verbosity (`AT+CMEE`) — the same error, three ways

Real modems can report errors at three levels of detail, set by `AT+CMEE`:

| CMEE mode | On error you get | Example |
|---|---|---|
| 0 (default) | a plain result code | `ERROR` |
| 1 | a numeric coded error | `+CME ERROR: 100` |
| 2 | a human-readable error | `+CME ERROR: unknown` |

This matters for a *test* project specifically: a conformance harness often sets
`AT+CMEE=2` first so failures are legible. Implementing it means our error replies
can no longer be a hard-coded string — they have to be *formatted* based on the
current CMEE mode. That's the small refactor in today's edits.

### 3. Defensive programming / robustness (the testing mindset)

A device under test will be sent malformed, truncated, and unexpected input — on
purpose. A well-built simulator (and later, harness) must **never crash** on bad
input; it should fail *gracefully* with an error and keep serving. Today we make
sure things like an empty line, `AT+`, `AT+CFUN=`, or random bytes all produce a
clean error instead of an exception. Two ideas worth naming:

- **Validate at the boundary.** Check inputs (is the cid a number? is the value 0
  or 1?) before using them.
- **Fault isolation.** Wrap command handling so an unexpected bug in one handler
  becomes a modem `ERROR`, not a dead connection. "Don't let one bad command take
  down the server."

### 4. Why freeze the simulator now (scope discipline)

The simulator is *scaffolding* — its job is to give the harness something
realistic to test. It is tempting to keep adding commands, but every hour on the
simulator is an hour not spent on the fault-classification work that actually sells
you (per the project guardrails). So after today we **freeze** it at ~14 commands
and shift to the harness. Freezing scope on purpose, and being able to say why, is
a maturity signal in itself.

---

## Part A — Edit `simulator/commands.py` (five targeted changes)

### Edit 1 — add two fields to `ModemState`

Find the `ModemState` dataclass. Add the two new fields shown, keeping the existing
ones:

```python
    attached: bool = False      # AT+CGATT packet-service attach state
    cmee_mode: int = 0          # AT+CMEE error verbosity: 0 plain, 1 numeric, 2 verbose
    pdp_contexts: dict = field(default_factory=dict)  # cid -> (pdp_type, apn)
    reg_state: RegState = field(default=RegState.NOT_REGISTERED)
```

(You already import `field` from `dataclasses` — it's used by `reg_state`. If not,
make the import line `from dataclasses import dataclass, field`.)

### Edit 2 — add an error-formatting helper

Right below the `_ok(...)` helper, add `_format_error`. This turns our internal
`ERROR` sentinel into whatever the current CMEE mode calls for:

```python
def _format_error(state: ModemState) -> str:
    """Format an error according to the modem's AT+CMEE verbosity setting.

    Mode 0 -> "ERROR" (plain). Mode 1 -> "+CME ERROR: 100" (numeric).
    Mode 2 -> "+CME ERROR: unknown" (verbose text). Centralizing this means
    handlers just signal failure by returning the ERROR sentinel, and we decide
    the wording here in one place.
    """
    if state.cmee_mode == 1:
        return "+CME ERROR: 100"       # 100 = "unknown" in the standard's table
    if state.cmee_mode == 2:
        return "+CME ERROR: unknown"
    return "ERROR"
```

### Edit 3 — add the two new command handlers

Add these alongside your other `_cmd_*` handlers (e.g. after `_cmd_cops`):

```python
def _cmd_cmee(state, form, value):
    # Set/read error-report verbosity.
    if form == "read":
        return _ok(f"+CMEE: {state.cmee_mode}")
    if form == "write":
        if value in ("0", "1", "2"):
            state.cmee_mode = int(value)
            return _ok()
        return ERROR
    if form == "test":
        return _ok("+CMEE: (0-2)")
    return ERROR


def _define_pdp_context(state, value):
    """Parse and store one PDP context from an AT+CGDCONT write.

    Expected value: <cid>,"<PDP_type>","<APN>"   e.g.  1,"IP","internet"
    We validate every field and return ERROR on anything malformed rather than
    raising — the "validate at the boundary" idea from the notes.
    """
    # Split on commas and strip spaces + surrounding quotes from each field.
    parts = [p.strip().strip('"') for p in value.split(",")]
    if len(parts) < 2:
        return ERROR                          # need at least cid + type
    cid_str, pdp_type = parts[0], parts[1].upper()   # normalize type, keep APN as typed
    if not cid_str.isdigit():
        return ERROR
    cid = int(cid_str)
    if not (1 <= cid <= 16):                   # standard allows contexts 1..16
        return ERROR
    if pdp_type not in ("IP", "IPV6", "IPV4V6"):
        return ERROR
    apn = parts[2] if len(parts) >= 3 else ""
    state.pdp_contexts[cid] = (pdp_type, apn)
    return _ok()


def _cmd_cgdcont(state, form, value):
    # Define / list PDP (data connection) contexts.
    if form == "write":
        return _define_pdp_context(state, value)
    if form == "read":
        if not state.pdp_contexts:
            return _ok()                       # nothing defined yet -> just OK
        lines = []
        for cid in sorted(state.pdp_contexts):
            pdp_type, apn = state.pdp_contexts[cid]
            lines.append(f'+CGDCONT: {cid},"{pdp_type}","{apn}","",0,0')
        return _ok("\r\n".join(lines))
    if form == "test":
        return _ok('+CGDCONT: (1-16),"IP",,,(0-1),(0-1)')
    return ERROR
```

### Edit 4 — register the two commands in the dispatch table

Add two entries to `EXTENDED_COMMANDS`:

```python
    "COPS": _cmd_cops,
    "CMEE": _cmd_cmee,
    "CGDCONT": _cmd_cgdcont,
}
```

### Edit 5 — harden `handle_command` (error formatting + fault isolation)

Replace your `handle_command` function with this version. Changes: it routes all
errors through `_format_error`, and it wraps the handler call so an unexpected
exception becomes a clean error instead of crashing the connection.

```python
def handle_command(line: str, state: ModemState) -> str:
    """Return the response body for one AT command line.

    Basic commands match exactly; extended (AT+...) commands are parsed into
    (verb, form, value) and routed. All errors are formatted per AT+CMEE. Any
    unexpected exception in a handler is contained and turned into a modem error,
    so one bad command can never take down the server (fault isolation).

    Command keywords are case-insensitive, but argument VALUES keep their case
    (e.g. an APN in AT+CGDCONT), so we do NOT uppercase the whole line.
    """
    stripped = line.strip()
    upper = stripped.upper()

    if upper in BASIC_COMMANDS:
        return BASIC_COMMANDS[upper](state)

    parsed = _parse_extended(stripped)         # original case in; parser upper-cases the verb
    if parsed is None:
        return _format_error(state)            # not a basic or extended command
    verb, form, value = parsed

    handler = EXTENDED_COMMANDS.get(verb)
    if handler is None:
        return _format_error(state)            # unknown extended command

    try:
        result = handler(state, form, value)
    except Exception:
        # Defensive boundary: never let a handler bug crash the connection.
        return _format_error(state)

    # Handlers signal failure with the ERROR sentinel; format it per CMEE here.
    if result == ERROR:
        return _format_error(state)
    return result
```

- [ ] All five edits applied to `commands.py`.
- [ ] `server.py` still unchanged.

---

## Part B — Test by hand

Start the simulator (`python -m simulator.server`) and connect
(`nc localhost 5050`). Send `ATE0` first, then:

```
AT+CGDCONT=1,"IP","internet"   -> OK
AT+CGDCONT?                    -> +CGDCONT: 1,"IP","internet","",0,0   then OK
AT+CGDCONT=99,"IP","x"         -> ERROR        (cid out of range 1-16)
AT+BOGUS                       -> ERROR        (CMEE is 0 -> plain)
AT+CMEE=2                      -> OK
AT+BOGUS                       -> +CME ERROR: unknown   (now verbose)
AT+CMEE=1                      -> OK
AT+BOGUS                       -> +CME ERROR: 100       (now numeric)
```

- ✅ *Worked when:* the same bogus command changes its error wording as you change
  CMEE. That's the whole point of `AT+CMEE`.

---

## Part C — Automated tests (including malformed input)

Append to `test_simulator.py`:

```python
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
```

**Run them:**

```bash
pytest
```

- ✅ *Worked when:* all pass (23 from before + 6 new = **29 passed**).

---

## Part D — Document the frozen command list in the README

Open `README.md` and add this section (it's also the "freeze" record — the
official list of what the simulator supports). Replace/expand the stub README with
at least this:

```markdown
## Supported AT commands (simulator — frozen after Day 6)

| Command | Form(s) | What it does |
|---|---|---|
| `AT` | execute | Attention / liveness check -> OK |
| `ATE0` / `ATE1` | basic | Turn command echo off / on |
| `AT+CGMI` | execute | Manufacturer identification |
| `AT+CGMM` | execute | Model identification |
| `AT+CIMI` | execute | IMSI (subscriber id); requires ready SIM |
| `AT+CSQ` | execute | Signal quality (+CSQ: rssi,ber) |
| `AT+CPIN` | read / write | SIM status; write a PIN to unlock |
| `AT+CFUN` | read / write / test | Phone functionality (radio on/off) |
| `AT+CREG` | read / write / test | Network registration status |
| `AT+CGATT` | read / write | Packet-service attach/detach |
| `AT+COPS` | read / write / test | Operator selection / name |
| `AT+CGDCONT` | read / write / test | Define/list PDP (data) contexts |
| `AT+CMEE` | read / write / test | Error-report verbosity (0/1/2) |

All commands follow public 3GPP TS 27.007. Unknown commands and malformed input
return an error (wording depends on the AT+CMEE setting) and never crash the
server.
```

- [ ] README updated with the command table.

---

## Part E — Docker sanity + push

```bash
docker build -t modem-harness . && docker run --rm modem-harness
git add .
git commit -m "Day 6: PDP context (CGDCONT) + error verbosity (CMEE) + input hardening; freeze simulator; document commands"
git push
```

- ✅ **DAY 6 IS DONE when:** CI is green with 29 tests, the CMEE demo works, and the
  README lists the frozen command set.

---

## FREEZE — simulator is done

From here on, **do not add features to the simulator.** The only future change is
fault injection on Day 12 (making it misbehave on purpose). If you catch yourself
wanting to add a command, that's scope creep — note it and move on. The next phase
is the actual product: the **conformance harness**.

---

## If something breaks

- **`field` is not defined:** your import at the top of `commands.py` must be
  `from dataclasses import dataclass, field`.
- **`AT+CGDCONT?` shows nothing:** you haven't defined a context yet in this
  connection — send an `AT+CGDCONT=1,"IP","internet"` first. (State is
  per-connection, so a fresh `nc` starts empty.)
- **CMEE error wording doesn't change:** confirm Edit 5 (the new `handle_command`)
  is in place — the old version returned a hard-coded `"ERROR"` and ignored CMEE.
- **A malformed-input test raises instead of failing cleanly:** the `try/except`
  in `handle_command` (Edit 5) is what converts exceptions to errors — make sure it
  wraps the `handler(...)` call.
- **CI red, local green:** confirm `commands.py`, `test_simulator.py`, and
  `README.md` were all committed.

---

## Progress log (updated as we go)

*(Fill in as you work through today.)*

---

*When CI is green with 29 tests and the simulator is frozen, Phase 1 is DONE. Day 7
starts Phase 2 — the conformance harness: a YAML test-plan format and a pytest
driver that reads it and drives the simulator through a Transport interface (the
one that later swaps in real hardware).*
