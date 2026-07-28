# Review — Interview Prep (living doc, updated as the project grows)

A consolidated, interview-focused review of everything built so far. Pairs with
`LEARNING_NOTES.md` (per-day concepts + flashcards); this doc adds the connective
tissue: the pitch, the architecture, the cross-cutting themes, honest limitations,
and a mock-interview drill. Updated a little each day.

**What exists so far (through Day 9):** a cellular modem *simulator* (a TCP server
that speaks 14 AT commands, with a registration state machine) and a *working
conformance harness* — declarative YAML test plans, a Transport interface, and a
runner with timeouts + retries. Tests run every YAML case against a live simulator;
~50 automated tests, green CI, containerized with Docker.

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
- **pytest discovery** — `test_`* functions, `Test`* classes (hence
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



### F. Harness runtime (Days 8–9)

- **Transport interface (dependency inversion).** Driver talks to an abstract
`Transport` (open/close/send), not sockets. TCP now, serial (real hardware) later
— swap = one new class, zero driver changes. Architecture name:
**port-and-adapter / hexagonal**.
- **pytest fixtures + parametrization.** A fixture starts the simulator in a
background thread on an **ephemeral port** (port 0 → OS picks a free one);
parametrization turns each YAML case into its own pass/fail result. Per-connection
state gives free test isolation.
- **Timeouts (deadline pattern).** Bounded waits — a hang blocks the whole run.
`send()` raises `TimeoutError` at the deadline.
- **Retries + exponential backoff.** Absorb *transient* failures, but *record the
attempt count* so retries can't silently mask a persistent bug. Backoff grows the
wait each try; production adds jitter.
- **Test doubles / DI.** Because the runner depends on the interface, tests inject a
`FakeTransport` to drive the timeout/retry paths deterministically. Stub = canned
answers, mock = also asserts calls, fake = working substitute (ours).



## 4. Design decisions to defend ("why not the alternative?")


| Decision              | Chose                          | Instead of              | One-line reason                                      |
| --------------------- | ------------------------------ | ----------------------- | ---------------------------------------------------- |
| Transport             | TCP                            | UDP                     | AT is a reliable, ordered, line-based stream         |
| Command routing       | Dispatch table                 | if/elif chain           | Readable, constant-time, open/closed                 |
| Registration          | Derived FSM                    | Hand-set flags          | Single source of truth, no drift                     |
| Illegal ops           | Guard → ERROR                  | Allow / crash           | Mirrors real hardware; it's the point of conformance |
| Test cases            | YAML data                      | Python code             | Non-coders can add tests; plan ≠ engine              |
| Concurrency           | Threads                        | asyncio                 | Simplest thing that stops blocking; easy to explain  |
| YAML parsing          | `safe_load`                    | `load`                  | Avoids arbitrary-object/code execution               |
| Error handling        | Graceful (sim) / loud (loader) | One rule everywhere     | Match strategy to trust level of the input           |
| Driver ↔ modem        | Transport interface            | Direct socket calls     | Swap in real hardware with one new class             |
| Waiting on device     | Bounded timeout + retries      | Wait forever / one shot | Never hang; absorb transient blips, record attempts  |
| Testing failure paths | Injected fake transport        | A real flaky device     | Deterministic, fast, no hardware                     |


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



## 9. Mock-interview answers (say these out loud)



### 1. Why TCP and not UDP for a modem simulator?

AT is a reliable, ordered, line-based command stream — you send a command, get a
complete response, in order. TCP gives that: connection-oriented, ordered delivery,
retransmits lost packets. UDP is fire-and-forget datagrams with no ordering
guarantee; you'd reinvent reliability and framing on top. Real modems are serial
streams; TCP is the network analogue of that stream.

### 2. What's the difference between binding to `0.0.0.0` and `127.0.0.1`?

`127.0.0.1` accepts connections only from the same machine (localhost). `0.0.0.0`
listens on all interfaces, so other containers or hosts on the network can reach
you. We bind `0.0.0.0:5050` because docker-compose clients talk to the simulator by
service name over the shared network — localhost-only would break that.

### 3. Walk me through what happens when a modem registers on a network.

1. Confirm SIM is ready (`AT+CPIN?` → READY).
2. Turn radio on (`AT+CFUN=1`) — that drives registration.
3. Modem searches and registers (home or roaming).
4. Read status (`AT+CREG?`) — e.g. `+CREG: 0,1` for home.
5. Attach packet/data service (`AT+CGATT=1`) — separate from voice registration.
6. Optionally read operator (`AT+COPS?`).

In our sim, registration is *derived*: SIM ready + radio on → `REGISTERED`
immediately via `_recompute_registration`. Real hardware has timing and cell
selection; we keep it deterministic on purpose.

### 4. What does `+CREG: 0,5` mean?

`+CREG: <n>,<stat>`. First number is reporting mode (`n` — how/whether the modem
unsolicited-reports registration changes). Second is status: **5 = registered,
roaming**. Contrast: `0` not registered, `1` home, `2` searching, `3` denied.
So `0,5` = mode 0, currently registered on a roaming network.

### 5. Why model registration as a state machine instead of a set of booleans?

Registration is always in exactly one of a fixed set of states, with defined
transitions — that's an FSM. Booleans like `is_registered` + `is_searching` can
drift into impossible combos. We go further: we don't hand-set `reg_state`; we
store inputs (`sim_ready`, `functionality`) and *derive* state in one place. Single
source of truth, illegal states hard to represent, guards easy to test.

### 6. You send `AT+CGATT=1` before registering — what happens and why?

`ERROR`. Guard condition in the CGATT handler: attach is only allowed if
`reg_state` is `REGISTERED` or `ROAMING`. Attaching to packet service without
network registration is illegal on real hardware; modeling that rejection *is*
conformance testing in miniature. Our YAML plan covers it: radio off, then
`CGATT=1`, expect `ERROR`.

### 7. Why did you refactor to a dispatch table?

If/elif chains grow brittle — every new command touches the same function. A dict
of verb → handler is O(1), readable, and open/closed: add a command by adding an
entry, not rewriting a ladder. Basic commands and extended (`AT+`) verbs each have
their own table; `handle_command` only routes.

### 8. Why are your test cases YAML instead of Python?

Plan vs engine. Cases are *data* (send, expect, timeout, retries, preconditions);
the runner is *code*. Non-coders can add tests by editing YAML; the engine never
changes. One driver runs every plan. That's how real conformance suites scale —
hundreds of cases, one harness.

### 9. Why `yaml.safe_load` and not `yaml.load`?

`yaml.load` can construct arbitrary Python objects from the file — that's a
code-execution risk on untrusted or even casually shared YAML. `safe_load` only
builds basic types (dict, list, str, int). Always use it for external config/plans.

### 10. Simulator swallows bad input; loader raises — why the difference?

Match error strategy to trust level. The simulator models a *device under test*:
hostile or garbage AT input must never crash the connection — return `ERROR`,
contain handler exceptions. The YAML loader is *developer config*: a malformed plan
is a bug we want loud and immediate (`ValueError` with where it failed). Same
project, opposite policies on purpose.

### 11. Unit test vs integration test in your project?

**Unit:** call `handle_command` / `load_plan` / `run_case` directly — no sockets.
Command logic and runner paths (including `FakeTransport` for timeouts/retries) stay
fast and deterministic. **Integration:** real TCP — fixture starts the simulator on
an ephemeral port, `TcpTransport` sends AT over the wire, assert responses. Proves
framing, echo, and networking work end-to-end.

### 12. Tell me about a bug you hit and how you found it.

Pick one (30-second story):

- **Port 5000 in use** → macOS AirPlay Receiver. `lsof -i :5000`, moved to 5050.
Lesson: diagnose the environment, don't only stare at your code.
- **APN came back uppercased** → whole-line `.upper()` mangled quoted data in
`AT+CGDCONT`. Fix: uppercase only the verb; preserve argument case. Lesson:
keywords are case-insensitive; string payloads are not.
- **pytest collected** `TestCase`**/**`TestPlan` → `Test`* naming convention.
`__test__ = False`. Lesson: know how your test runner discovers tests.



### 13. What are the limitations of your simulator?

Scaffolding, not a full 3GPP stack — ~14 commands. `SEARCHING` / `DENIED` /
`ROAMING` exist in the enum but the normal path doesn't reach them yet (fault
injection comes later). Registration is instant and deterministic, not timed cell
selection. Identity values (manufacturer, IMSI) are invented from public
TS 27.007. It's enough to drive a real harness design; it's not a production modem
model.

### 14. How does your CI know the code is safe to merge?

GitHub Actions on every push/PR: checkout → Python 3.13 → `pip install -r requirements.txt` → `pytest`. Green means unit + integration suite passed in a
clean environment. Docker keeps the runtime reproducible locally the same way.
CI doesn't prove hardware correctness — it proves *this repo's tests* still pass.

### 15. If you swapped the simulator for a real modem, what would change?

Only the transport. The driver talks to an abstract `Transport` (`open` / `close` /
`send`), not sockets. Today: `TcpTransport` to the sim. For hardware: a
`SerialTransport` implementing the same interface. Runner, YAML plans, and
expectations stay untouched — that's dependency inversion / port-and-adapter. The
abstraction exists *so* this swap is one new class.

---

*Living doc — update answers when Day 10+ changes architecture or adds fault
classification.*