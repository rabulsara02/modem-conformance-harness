# Learning Notes

A running, plain-English reference for the concepts behind this project — written
so you can **explain what you built, from scratch, to an interviewer.** New topics
get appended as we hit them. Each section has: the concepts, and **interview
flashcards** (the questions a test/systems interviewer actually asks).

> How to use this: skim the concepts when you build a file; drill the flashcards
> before interviews. If you can answer a flashcard out loud without reading, you
> own it.

---

## Day 3 — Sockets, TCP, and the modem simulator's server

### The concepts

**1. Socket.** One endpoint of a network conversation — like a phone handset.
Identified by an IP address (which machine) + a port (which program). Our server
opens one, waits for callers, and talks back.

**2. TCP vs UDP.** TCP is reliable, ordered, connection-based, and behaves like a
continuous *stream* of bytes — so we read it line by line. UDP is fire-and-forget
with no delivery guarantees (good for video/games). Modems + AT commands are
stream-like, so TCP fits.

**3. Client/server model.** The server *listens/binds* and waits (our simulator —
passive, only responds). The client *connects* (`nc`, later the test harness). The
server never reaches out first.

**4. `0.0.0.0` vs `127.0.0.1`.** `127.0.0.1` (localhost) = accept only from this
same machine. `0.0.0.0` = accept on all interfaces, so *other containers/machines*
can reach us. Binding to localhost is exactly what would have broken the Day 2
two-container demo.

**5. Ports.** 0–65535. Picks which program gets the traffic. <1024 are privileged
(80=HTTP, 443=HTTPS, 22=SSH). We use 5000: high, free, memorable.

**6. Bytes vs strings.** Networks move raw *bytes*, not text. `.encode()` string →
bytes to send; `.decode()` bytes → string on receive. This is why you see `b"..."`,
`reply.encode()`, `raw.decode()`. The #1 beginner socket bug is forgetting this
boundary.

**7. Line-based framing.** TCP is a byte stream with **no built-in message
boundaries** — *you* decide where a message ends. We use the newline `\n`, and
`readline()` reads up to and including it. AT commands are line-terminated, so it
fits.

**8. `socketserver` (what it hides).** Raw sockets require manual
`socket()/bind()/listen()/accept()` loops. `socketserver` wraps all that; you just
subclass a handler and write `handle()`. `StreamRequestHandler` also wraps the
socket in file-like objects: `self.rfile` (read) and `self.wfile` (write).

**9. Threading — `ThreadingTCPServer`.** Socket reads *block* (pause until data
arrives). One quiet client would freeze a single-threaded server for everyone.
Threading gives each connection its own thread, so clients don't block each other.

**10. `time.monotonic()`.** A forward-only clock, unaffected by system-clock
changes — the correct tool for measuring *durations* (latency). `time.time()` is
for wall-clock date/time, not intervals.

**11. `logging` vs `print`.** `logging` gives timestamped, leveled
(INFO/WARNING/ERROR), filterable, redirectable output. Every command in/response
out is logged — our debugging tool AND our metrics source.

**12. `if __name__ == "__main__"`.** "Only run this if executed directly, not if
imported." It's why tests can `import` the simulator package without launching a
server.

### Interview flashcards — Day 3

- **Q: What does your simulator do at the network level?**
  A: Opens a TCP socket, binds it to a port, and serves clients that connect —
  reading newline-terminated AT commands and writing back responses.

- **Q: TCP or UDP, and why?**
  A: TCP — it's reliable, ordered, and stream-based, which matches a modem's
  line-oriented command/response protocol. UDP's no-guarantee model would drop or
  reorder commands.

- **Q: Why bind to `0.0.0.0` instead of `127.0.0.1`?**
  A: So processes outside this machine/container can connect. localhost would only
  accept local connections and break the containerized setup.

- **Q: TCP has no message boundaries — how do you know where one command ends?**
  A: I frame on the newline: read one line at a time with `readline()`. The
  protocol defines `\n` as the delimiter.

- **Q: How do you send a Python string over a socket?**
  A: Encode it to bytes first (`.encode()`), because sockets transmit bytes;
  decode on the way back (`.decode()`).

- **Q: Why threading?**
  A: Socket reads block. Without a thread per connection, one idle client would
  stall all others. `ThreadingTCPServer` isolates them.

- **Q: Why `time.monotonic()` and not `time.time()` for latency?**
  A: `monotonic()` never goes backward and ignores system-clock adjustments, so
  it's correct for measuring elapsed time.

- **Q: Your server won't start with "Address already in use" — what's happening
  and how do you debug it?**
  A: Another process already bound that port. I find it with `lsof -i :<port>`,
  then either stop that process or bind to a different free port. (Real example
  from this project: macOS AirPlay Receiver owns port 5000, so I moved the
  simulator to 5050.)

### Design decision to be able to defend (Day 3)

**Splitting "plumbing" (server.py) from "brain" (commands.py).** Networking and
command logic live in separate files so the command logic can be unit-tested with
no sockets — fast, deterministic, no ports or timing. This is *testability by
design*, which is the whole point of a test-engineering role.

---

## Day 4 — Dispatch tables and the modem's identity commands

### The concepts

**1. Dispatch table (vs if/elif chain).** A dict mapping each command string to a
handler function: `COMMANDS = {"AT+CSQ": _cmd_csq, ...}`, then
`handler = COMMANDS.get(cmd)`. Readable (each command is its own function),
extensible (add a command = one function + one dict entry, touch nothing else —
the *open/closed principle*), constant-time lookup, and independently testable.
Names to drop: *table-driven methods* / *Command pattern*.

**2. Basic vs extended AT commands.** Basic = short, prefix-free (`AT`, `ATE0`).
Extended = `AT+KEYWORD`, from 3GPP TS 27.007. Extended commands have four *forms*
by suffix: **test** `=?` (what's supported), **read** `?` (current value),
**write** `=value` (set it), **execute** (no suffix, do it / return info). Day 4
uses read (`AT+CPIN?`) and execute (`AT+CGMI`, `AT+CSQ`).

**3. The cellular commands.**
- `AT+CGMI` / `AT+CGMM` — manufacturer / model identification.
- `AT+CIMI` — the **IMSI** (International Mobile Subscriber Identity): the SIM's
  unique subscriber ID = MCC (country) + MNC (network) + MSIN (subscriber).
  Requires a ready SIM.
- `AT+CSQ` — signal quality `+CSQ: <rssi>,<ber>`: RSSI 0–31 (99=unknown), BER 0–7
  (99=unknown).
- `AT+CPIN?` — SIM status: `READY` (usable) vs `SIM PIN` (locked). Gates
  registration on Day 5.

**4. Response format.** A data query returns an **information response** line (the
data) then a final **result code** (`OK`). Modeled by the `_ok(info)` helper.

**5. Refactoring behind a stable interface.** We rewrote the internals of
`commands.py` but kept `handle_command(line, state)` identical, so `server.py`
needed zero changes. "Change the implementation, keep the interface" is a core
engineering habit.

### Interview flashcards — Day 4

- **Q: Why a dispatch table instead of if/elif?**
  A: Readability, constant-time lookup, and extensibility — new commands are added
  without modifying existing code (open/closed principle). Each handler is also
  unit-testable in isolation.

- **Q: What are the four forms of an extended AT command?**
  A: Test (`=?`), read (`?`), write (`=value`), and execute (no suffix). `AT+CPIN?`
  is a read; `AT+CIMI` is an execute.

- **Q: What is an IMSI and why does AT+CIMI require the SIM to be ready?**
  A: The IMSI is the subscriber's unique identity, stored on the SIM (MCC+MNC+MSIN).
  If the SIM isn't unlocked/ready, there's no IMSI to read, so the modem returns
  ERROR.

- **Q: What does `+CSQ: 20,99` mean?**
  A: RSSI 20 of 31 (a decent signal) and BER 99 = unknown/not measured.

- **Q: You added commands but didn't touch server.py — why not?**
  A: The command logic lives behind a stable function (`handle_command`); I changed
  its internals (if/elif → table) without changing its interface, so the caller was
  unaffected.

### Design decisions to be able to defend (Day 4)

- **Table-driven dispatch** for scalability and testability.
- **Stable public interface** while refactoring internals (server.py untouched).
- **SIM-gating `AT+CIMI`** to mirror real hardware behavior — sets up the Day 5
  state machine.

---

## Day 5 — Finite state machines and network registration

### The concepts

**1. Finite state machine (FSM).** A fixed set of states; the system is in exactly
one at a time; transitions move between them on events. Modem registration is a
natural FSM (not registered / searching / registered / roaming / denied). We use
one because it mirrors the standard, is directly testable, and makes illegal states
impossible.

**2. The real registration sequence.** SIM ready (`AT+CPIN?`) → radio on
(`AT+CFUN=1`) → search & register (home or roaming) → check status (`AT+CREG?`) →
attach packet/data service (`AT+CGATT=1`) → see operator (`AT+COPS?`). Note voice
registration and data attach are *separate* steps.

**3. The four commands + CREG codes.** CFUN sets functionality (1=radio on,
0=off — the main driver). CREG reports status as `+CREG: <n>,<stat>`. CGATT
attaches/detaches packet service. COPS gives the operator name.
CREG stat codes: **0** not registered, **1** registered home, **2** searching,
**3** denied, **4** unknown, **5** roaming.

**4. Parsing AT command forms.** Extended commands have four forms by suffix:
`=?` test, `?` read, `=value` write, bare = execute. Our `_parse_extended()`
returns `(verb, form, value)` and handlers branch on the form.

**5. Derived state vs stored state.** Don't store `reg_state` as an independent
variable set by hand in many places (drifts out of sync). Store the *inputs*
(`sim_ready`, `functionality`) and derive `reg_state` in one function
(`_recompute_registration`). Single source of truth. Principle: "derive, don't
duplicate."

**6. Guard conditions.** Some transitions are illegal (attaching before
registering). A guard (`if precondition not met: return ERROR`) rejects them, like
real hardware. Modeling and testing illegal transitions *is* conformance testing —
the most on-topic code in the project for test/validation roles.

### Interview flashcards — Day 5

- **Q: What's a finite state machine and why model registration as one?**
  A: A model with a fixed set of states, one active at a time, and defined
  transitions. Registration fits it exactly; an FSM makes the behavior testable and
  makes invalid states unrepresentable.

- **Q: Walk me through a modem registering on a network.**
  A: Confirm the SIM is ready, turn the radio on (CFUN=1), the modem searches and
  registers (home or roaming), you read status with CREG, then attach data service
  with CGATT and can read the operator with COPS.

- **Q: What does `+CREG: 0,1` mean? And `0,5`?**
  A: The first number is the reporting mode; the second is the status — 1 =
  registered on the home network, 5 = registered while roaming.

- **Q: How do you prevent an illegal transition, like attaching before
  registration?**
  A: A guard condition: the CGATT=1 handler checks the state is REGISTERED/ROAMING
  first and returns ERROR otherwise — mirroring real hardware.

- **Q: Why derive the registration state instead of storing it?**
  A: To keep a single source of truth. Storing it separately risks it drifting out
  of sync with the inputs; deriving it in one place guarantees consistency.

### Design decisions to be able to defend (Day 5)

- **FSM with an `Enum`** for states (type-safe, self-documenting vs bare strings).
- **Derived state** via `_recompute_registration` — single source of truth.
- **Guard conditions** rejecting illegal transitions — the conformance mindset.
- **A parser** turning AT forms into `(verb, form, value)`, extending the dispatch
  table rather than replacing it.

---

## Day 6 — PDP context, error verbosity, and defensive programming

### The concepts

**1. PDP context (`AT+CGDCONT`).** A modem's definition of a data connection:
a **cid** (id), a PDP type (IPv4/IPv6), and an **APN** (Access Point Name — the
gateway into a carrier's data network). `AT+CGDCONT=1,"IP","internet"` defines it;
`AT+CGDCONT?` lists defined contexts. It sits on top of registration to enable a
data session.

**2. Error verbosity (`AT+CMEE`).** The same failure, three ways: mode 0 → `ERROR`,
mode 1 → `+CME ERROR: 100` (numeric), mode 2 → `+CME ERROR: unknown` (text).
Harnesses often set `CMEE=2` for legible failures. Implementing it forced errors to
be *formatted* from a central helper instead of a hard-coded string.

**3. Defensive programming / robustness.** A device (or simulator) under test gets
malformed input on purpose and must never crash. Two ideas: **validate at the
boundary** (check the cid is numeric and in range before using it) and **fault
isolation** (wrap handler calls so one bug becomes a modem `ERROR`, not a dead
connection). This is the tester's mindset made concrete.

**4. Scope discipline / freezing.** The simulator is scaffolding; we froze it at
~14 commands so effort shifts to the fault-classification work that differentiates
the project. Deliberately capping scope — and explaining why — is a maturity signal.

### Interview flashcards — Day 6

- **Q: What's a PDP context / APN?**
  A: A PDP context is the modem's definition of a data connection — an id, IP type,
  and an APN, which is the named gateway into the carrier's data network.

- **Q: What does AT+CMEE do?**
  A: Sets error-report verbosity: plain `ERROR`, numeric `+CME ERROR: <code>`, or
  verbose `+CME ERROR: <text>`. Test harnesses use verbose mode for readable
  failures.

- **Q: How do you make sure malformed input doesn't crash your server?**
  A: Validate inputs at the boundary before using them, and wrap command handling
  in a try/except so an unexpected error becomes a clean error response instead of
  taking down the connection.

- **Q: Why did you stop adding features to the simulator?**
  A: It's scaffolding for the harness. More simulator features have diminishing
  value; the differentiating work is fault injection and classification, so I froze
  scope and moved on.

- **Q: Why did the modem print my command back to me over `nc`?**
  A: That's command echo (ATE1, on by default) — the modem repeats each command
  before replying. The terminal also shows what I type locally, so with echo on I
  see it twice. `ATE0` turns the modem's echo off.

- **Q: (Bug we hit) Your APN came back uppercased — why, and how did you fix it?**
  A: `handle_command` was uppercasing the entire line, which is fine for the
  case-insensitive command keyword but wrong for a quoted argument like the APN.
  Fix: uppercase only the verb, and leave argument values as typed. Lesson:
  in a protocol, keywords are case-insensitive but string *data* is case-sensitive.

### Design decisions to be able to defend (Day 6)

- **Centralized error formatting** (`_format_error`) driven by CMEE — handlers just
  signal failure, wording is decided in one place.
- **Boundary validation + fault isolation** so the server survives garbage input.
- **Case handling:** normalize the command keyword, preserve argument values —
  keywords are case-insensitive, quoted data is not.
- **Freezing the simulator** to protect time for the high-value harness work.

---

## General learning tips (kept running)

- **Explain it out loud.** After each file, close the editor and narrate what it
  does and why. If you stall, that's the spot to re-read. Interviewers test the
  narration, not the typing.
- **"Why not the alternative?"** For every choice (TCP vs UDP, threading vs async,
  YAML vs JSON), know the one-sentence reason you didn't pick the other. That's
  what separates "I followed a tutorial" from "I made decisions."
- **Keep the metrics story straight.** This project's differentiator is numbers
  (pass rates, latency, fault-classification accuracy). Always know what you're
  measuring and why — it's instrumented from day one on purpose.
- **Commit messages are a log of your reasoning.** Write them like you're
  explaining the change to someone: "Day 3: split command logic from networking so
  it's unit-testable" beats "update files".

---

*Appended per day. Next up (Day 7): Phase 2 begins — the conformance harness. A
YAML test-plan format and a pytest driver that reads it and drives the simulator
through a Transport interface (the seam that later swaps in real hardware).*
