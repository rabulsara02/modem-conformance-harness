# Review Session 1 — Days 1–7 (Simulator + Harness foundation)

A consolidated, interview-focused review of everything built so far. Pairs with
`LEARNING_NOTES.md` (per-day concepts + flashcards); this doc adds the connective
tissue: the pitch, the architecture, the cross-cutting themes, honest limitations,
and a mock-interview drill.

**What exists so far:** a cellular modem *simulator* (a TCP server that speaks 14
AT commands, with a registration state machine) and the *foundation of a
conformance harness* (a declarative YAML test-plan format + validating loader).
36 automated tests, green CI, containerized with Docker.

---



## 1. The one-paragraph pitch (memorize the shape, not the words)

> "I built a conformance test harness for cellular modems. There's a simulator
> that emulates a modem over TCP — it parses AT commands and models network
> registration as a finite state machine, including realistic failure behavior like
> refusing to attach to data service before it's registered. Then there's a harness
> that runs declarative YAML test plans against it. The whole thing is
> containerized and runs in CI. The point of the project is the part validation
> teams actually care about: telling a *device* failure apart from a *harness*
> failure — which I build out with fault injection and classification."

Why this lands: it names the domain (cellular/AT), a real design concept (FSM),
the testing angle (declarative plans, CI), and the differentiator (fault
classification). It's the SGS conformance work, rebuilt as something you can show.

---



## 2. Architecture — how the pieces fit

```
   YAML test plans        harness/                     simulator/
   (testplans/*.yaml)     testplan.py  ── drives ──►   server.py   (networking)
        │  data              (loader)                     │  uses
        └──────────────►  [Day 8: driver] ── TCP ──►   commands.py (AT logic + FSM)
                                                           │
                                                    ModemState (per-connection memory)

   Docker packages it · GitHub Actions runs pytest on every push
```

Two separations are the backbone of the design, and both are deliberate:

1. **Plumbing vs brain (in the simulator).** `server.py` does networking only;
  `commands.py` does command logic only. Result: the logic is unit-testable with
   no sockets.
2. **Plan vs engine (in the harness).** Test cases are YAML *data*; the driver is
  *code*. Result: adding tests never touches the engine.

If you can draw this diagram and explain those two separations, you can explain the
project.

---



## 3. Concepts grouped by area (with the questions they invite)



### A. Networking

- **Socket / TCP vs UDP / client-server / ports.** TCP because AT is a reliable,
ordered, line-based stream. Server listens; client connects.
- `0.0.0.0` **vs** `127.0.0.1`**.** All interfaces vs localhost-only — the former lets
other containers/machines reach you. (Common gotcha question.)
- **Bytes vs strings.** Sockets move bytes; `.encode()`/`.decode()` at the edges.
- **Framing.** TCP has no message boundaries; we frame on newline via `readline()`.
- **Threading.** `ThreadingTCPServer` — blocking reads mean one client mustn't
freeze the rest.



### B. Cellular / domain

- **AT commands** and the **four forms** (test `=?`, read `?`, write `=v`,
execute).
- **Identity:** CGMI/CGMM (make/model), **CIMI/IMSI** (subscriber id = MCC+MNC+MSIN,
needs ready SIM), **CSQ** (RSSI 0–31/99, BER 0–7/99).
- **Registration FSM** and **CREG codes** (0 not-registered, 1 home, 2 searching,
3 denied, 5 roaming). CFUN drives it; CGATT attaches data; COPS names the
operator.
- **PDP context / APN** (CGDCONT) and **error verbosity** (CMEE: plain / numeric /
verbose).



### C. Software design

- **Dispatch table** over if/elif (readable, O(1), open/closed principle).
- **Finite state machine** with an `Enum` for registration.
- **Derived state** — store inputs (`sim_ready`, `functionality`), derive
`reg_state` in one place; single source of truth.
- **Guard conditions** — reject illegal transitions (attach before register →
ERROR). *This is conformance testing in miniature.*
- **Stable interface refactoring** — internals of `commands.py` changed repeatedly;
`handle_command()` and `server.py` never did.
- **Data-driven testing** — declarative YAML plans decoupled from the runner.



### D. Testing

- **Unit vs integration** — we test command logic directly (unit), no sockets.
- **pytest discovery** — `test_`* functions, `Test*` classes (hence
`__test__ = False` on our models).
- `pytest.raises` **/** `tmp_path` — assert-it-throws + throwaway temp files for
negative tests.
- **Error strategy by situation** — graceful for untrusted device input, loud for
developer config (the loader raises).
- **Boundary validation + fault isolation** — validate inputs, contain handler
exceptions so one bad command can't kill the server.



### E. Infra / DevOps

- **Docker / containers** — same environment everywhere; `docker run` proves the
image is self-contained.
- **docker-compose** — multiple services on a shared network, reachable by name.
- **CI / GitHub Actions** — tests run on every push; green = safe.
- **Dependencies** — `requirements.txt` lists *direct* deps (pytest, PyYAML);
transitives resolve automatically.

---



## 4. Design decisions to defend ("why not the alternative?")


| Decision        | Chose                          | Instead of          | One-line reason                                      |
| --------------- | ------------------------------ | ------------------- | ---------------------------------------------------- |
| Transport       | TCP                            | UDP                 | AT is a reliable, ordered, line-based stream         |
| Command routing | Dispatch table                 | if/elif chain       | Readable, constant-time, open/closed                 |
| Registration    | Derived FSM                    | Hand-set flags      | Single source of truth, no drift                     |
| Illegal ops     | Guard → ERROR                  | Allow / crash       | Mirrors real hardware; it's the point of conformance |
| Test cases      | YAML data                      | Python code         | Non-coders can add tests; plan ≠ engine              |
| Concurrency     | Threads                        | asyncio             | Simplest thing that stops blocking; easy to explain  |
| YAML parsing    | `safe_load`                    | `load`              | Avoids arbitrary-object/code execution               |
| Error handling  | Graceful (sim) / loud (loader) | One rule everywhere | Match strategy to trust level of the input           |


Being able to give the "instead of / because" for each is what separates "I
followed a tutorial" from "I made decisions."

---



## 5. Bugs & gotchas we hit (and what they show)

- **Port 5000 in use** → macOS AirPlay. Debugged with `lsof -i :5000`, moved to
  1. *Shows: you can diagnose, not just code.*
- **APN uppercased** → whole-line `.upper()` mangled quoted data. Fixed to
normalize only the keyword. *Shows: protocol case-sensitivity — keywords
case-insensitive, string data not.*
- **pytest collection warning** → `Test`* naming convention hit our models.
`__test__ = False`. *Shows: you understand pytest discovery.*
- **Double echo over** `nc` → not a bug; ATE1 echo + terminal local echo. *Shows:
you understand the protocol behavior you built.*

Interviewers love "tell me about a bug" — each of these is a clean 30-second story
with a root cause and a lesson.

---



## 6. Honest limitations (say these before they ask — it builds credibility)

- The simulator is **scaffolding**, deliberately capped at ~14 commands; it's not a
full 3GPP implementation.
- `SEARCHING`, `DENIED`, `ROAMING` states exist but the normal path doesn't reach
them yet — that's what **fault injection (Day 12)** is for.
- Registration is modeled **deterministically** (radio on + SIM ready → registered
immediately); real modems have timing, retries, and cell selection we don't
model.
- Identity values (manufacturer, IMSI) are **invented** — everything is built from
the *public* 3GPP TS 27.007, with no confidential/device-specific data.
- The harness so far only **loads** plans; it doesn't run them yet (Day 8).

Naming the scope on purpose — and why — is itself a maturity signal.

---



## 7. "Walk me through your project" — the narrative arc

1. **Motivation:** at SGS I did cellular conformance testing; I wanted to rebuild
  that skill as something demonstrable.
2. **Foundation first:** I set up CI and Docker on day one, before any real code,
  so I'd never be debugging infrastructure and features at the same time.
3. **Simulator:** a TCP server that parses AT commands, with registration modeled
  as a finite state machine, including guard conditions that refuse illegal
   operations.
4. **Harness:** declarative YAML test plans decoupled from the driver, so tests are
  data anyone can add.
5. **The differentiator (in progress):** fault injection + classification —
  distinguishing device failures from harness failures, which is what validation
   teams actually screen for.
6. **Throughout:** tested at every step, documented for learning, green CI.

---



## 8. Mock-interview drill (cover the answer, say it out loud)

1. Why TCP and not UDP for a modem simulator?
2. What's the difference between binding to `0.0.0.0` and `127.0.0.1`?
3. Walk me through what happens when a modem registers on a network.
4. What does `+CREG: 0,5` mean?
5. Why model registration as a state machine instead of a set of booleans?
6. You send `AT+CGATT=1` before registering — what happens and why?
7. Why did you refactor to a dispatch table?
8. Why are your test cases YAML instead of Python?
9. Why `yaml.safe_load` and not `yaml.load`?
10. Your simulator swallows bad input but your loader raises on it — why the
  difference?
11. Difference between a unit test and an integration test in your project?
12. Tell me about a bug you hit and how you found it.
13. What are the limitations of your simulator?
14. How does your CI know the code is safe to merge?
15. If you swapped the simulator for a real modem, what would change? (Answer: only
  the transport — TCP → serial — which is why Day 8 builds a Transport interface.)

If you can answer all 15 out loud without notes, you can carry a 30-minute
conversation about this project.

---



## 9. Mock-interview answers (speak these; don't memorize word-for-word)

**1. Why TCP and not UDP?**
AT commands are a reliable, ordered, line-based conversation: send a command, get
a response, in order. TCP gives that stream with delivery guarantees. UDP can drop
or reorder packets — fine for video, wrong for a modem command protocol. We also
frame on newline (`readline()`), which only makes sense on a continuous byte stream.

**2.** `0.0.0.0` **vs** `127.0.0.1`**?**
`127.0.0.1` accepts connections only from the same machine. `0.0.0.0` listens on
all interfaces, so other containers or hosts can reach the simulator. We need that
for docker-compose — the harness container connects to the sim by service name. Bind
to localhost and the two-container setup breaks.

**3. Walk through network registration.**
Inputs drive a derived FSM in `_recompute_registration`: SIM must be ready
(`AT+CPIN?` → `READY`) and radio on (`AT+CFUN=1`). Then we go to `REGISTERED`
(home). `AT+CREG?` reports that; `AT+COPS?` returns the operator; only then is
`AT+CGATT=1` (packet attach) allowed. Radio off (`CFUN=0`) or SIM not ready drops
registration and clears attach. Normal path is deterministic: ready SIM + radio on
→ registered immediately (no real cell-search timing).

**4. What does** `+CREG: 0,5` **mean?**
Format is `+CREG: <n>,<stat>`. `0` is the reporting mode (unsolicited off). `5`
means registered, roaming. In our enum that's `ROAMING`. Home network is `1`;
searching `2`; denied `3`; not registered `0`. Roaming isn't on the normal path
yet — it's reserved for fault injection.

**5. Why a state machine instead of booleans?**
Booleans drift — you can have `registered=True` and `searching=True` at once,
which is nonsense. An FSM has exactly one `reg_state`. We store the *inputs*
(`sim_ready`, `functionality`) and *derive* `reg_state` in one function, so there's
a single source of truth and no inconsistent combinations.

**6.** `AT+CGATT=1` **before registering — what happens?**
Guard condition: attach is only legal in `REGISTERED` or `ROAMING`. Otherwise we
return `ERROR`, like real hardware. That's conformance testing in miniature —
illegal sequences must fail cleanly, not crash or silently succeed. Deregistering
also clears `attached` so you can't stay attached without registration.

**7. Why a dispatch table?**
An if/elif chain for ~14 commands becomes unreadable and every new command edits
the same giant function. A dict maps command → handler: readable, O(1) lookup,
open/closed (add a handler + one table entry, touch nothing else). Each handler is
unit-testable alone. We kept `handle_command()` stable so `server.py` never needed
changes when we refactored.

**8. Why YAML test cases instead of Python?**
Plans are *data*; the driver is *code*. Non-coders can add cases by editing YAML.
One loader/runner executes every plan. Schema fields: `send`, `expect` /
`expect_regex`, optional `timeout_ms`, `retries`, `precondition`. Today we only
*load* and validate; Day 8 wires the driver.

**9. Why** `yaml.safe_load` **not** `yaml.load`**?**
`load` can construct arbitrary Python objects from the file — effectively code
execution from untrusted input. `safe_load` only builds plain data (dicts, lists,
strings). Test plans are files on disk; safer default costs nothing.

**10. Simulator swallows bad input; loader raises — why?**
Different trust models. The simulator models a *device under test* — hostile or
malformed AT must return `ERROR` and keep running (one bad command can't kill the
server). A malformed YAML plan is a *developer mistake* — fail loud with
`ValueError` so CI catches it immediately. Match error strategy to who produced the
input.

**11. Unit vs integration in this project?**
Unit: call `handle_command()` or `load_plan()` directly — no sockets, no ports,
fast and deterministic (36 tests today). Integration: open a real TCP (or later
serial) connection and drive the full path. That's Day 8 via a `Transport`
interface. We unit-tested the brain first so networking bugs don't pollute command
logic.

**12. A bug you hit.**
Pick one:

- **Port 5000 in use** — macOS AirPlay. `lsof -i :5000`, moved simulator to 5050.
- **APN uppercased** — whole-line `.upper()` mangled quoted APNs. Fixed: normalize
the keyword only; leave string data alone.
- **pytest collected** `TestCase`**/**`TestPlan` — `Test`* naming. Set `__test__ = False`.
- **Double echo over** `nc` — not a bug: terminal local echo + modem `ATE1` echo.

**13. Limitations of the simulator?**
Deliberately capped at ~14 public AT commands — scaffolding, not a full 3GPP
stack. `SEARCHING` / `DENIED` / `ROAMING` exist in the enum but the normal path
doesn't reach them (fault injection will). Registration is deterministic, not
real radio timing. Identity/IMSI values are invented; everything from public
TS 27.007. Harness loads plans but doesn't execute them yet.

**14. How does CI know it's safe to merge?**
GitHub Actions on every push/PR: checkout → Python 3.13 → `pip install -r requirements.txt` → `pytest`. Green means the suite passed in a clean environment.
We also prove the image with Docker (`docker run` runs pytest). Compose still uses
Day-2 stubs for two-container networking; full sim+harness wire-up comes later.

**15. Swap simulator for a real modem — what changes?**
Only the transport: TCP socket → serial (`/dev/ttyUSB`). Command logic, YAML plans,
timeouts, and (later) classification stay the same. That's why Day 8 introduces a
`Transport` interface (`send` / `open` / `close`) with a TCP implementation now and
a serial drop-in later — zero harness changes above that seam.

---

*Next: Day 8 — the driver that runs these YAML plans against the simulator through
a Transport interface (the seam that later swaps in real hardware, per Q15).*