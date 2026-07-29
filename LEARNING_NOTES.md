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

## Day 7 — Declarative test plans (YAML) and the harness

### The concepts

**1. Data-driven testing.** Define tests as *data* (YAML) instead of *code*. One
engine (the driver) runs many cases; adding a case means editing YAML, not Python.
Benefits: non-programmers can contribute tests, plan and engine are decoupled, and
the plan reads like a conformance spec.

**2. YAML.** A human-readable data format — indentation instead of braces. Great for
config and test definitions because it's easy to read and review.

**3. The schema.** Each case: `name`, `send`, and one of `expect` (substring) /
`expect_regex` (regex); optional `timeout_ms`, `retries`, `precondition`. Regex
covers pattern responses like `+CSQ: <digits>,<digits>`.

**4. `yaml.safe_load` vs `yaml.load`.** Always `safe_load` external files — plain
`load` can construct arbitrary Python objects (code-execution risk). `safe_load`
builds only basic types.

**5. Match error strategy to the situation.** Simulator = fail *gracefully* (models
untrusted device input, never crash). Loader = fail *loudly* (`raise ValueError` on
a malformed plan, because that's a developer error to surface immediately).

**6. pytest tools.** `pytest.raises(Exc)` asserts a block raises; `tmp_path` gives a
fresh temp directory to write throwaway (bad) files for negative tests.

### Interview flashcards — Day 7

- **Q: Why did you make test cases YAML data instead of Python code?**
  A: Data-driven testing — the plan is separate from the engine, non-coders can add
  cases, and the plan reads like a test specification. One driver runs them all.

- **Q: Why `yaml.safe_load` and not `yaml.load`?**
  A: `load` can instantiate arbitrary Python objects from the file (a code-execution
  risk); `safe_load` only produces basic types. Use safe_load on any external file.

- **Q: Your simulator swallows bad input but your loader raises on it — why the
  difference?**
  A: They're different situations. The simulator models a device receiving hostile
  input and must stay up. A malformed test plan is a developer mistake I want to fail
  fast and loudly so it's fixed immediately.

- **Q: How do you test that code correctly rejects bad input?**
  A: With `pytest.raises` — assert the call raises the expected exception — feeding
  it a deliberately broken input built in a `tmp_path` temp directory.

- **Q: (Warning we hit) pytest complained it couldn't collect your `TestPlan`
  class — why?**
  A: pytest auto-collects any class named `Test*` as a test class. My domain models
  `TestCase`/`TestPlan` matched that convention by accident. Setting
  `__test__ = False` on them opts them out. (Lesson: pytest discovers `test_*`
  functions and `Test*` classes by naming convention.)

### Design decisions to be able to defend (Day 7)

- **Declarative YAML plans** — data-driven, decoupled from the driver.
- **`safe_load`** for security.
- **Loud validation** with located error messages (contrasts with the simulator).
- **`expect` + `expect_regex`** to support both substring and pattern matching.

---

## Day 8 — Transport interface, fixtures, and running the plans

### The concepts

**1. Program to an interface (dependency inversion).** The driver talks to an
abstract `Transport` (open/close/send), never to sockets directly. TCP is one
implementation; serial (real hardware, Day 17) is another. Swapping hardware =
one new Transport, zero driver changes. Architecture name: **port-and-adapter /
hexagonal**.

**2. Abstract base classes (`ABC` / `@abstractmethod`).** Declare a class that
can't be instantiated and whose methods every subclass MUST implement — the
language enforces the contract.

**3. pytest fixtures.** Reusable setup a test depends on. A `yield` fixture does
setup → hand value to test → teardown. Ours starts the simulator in a thread and
shuts it down after.

**4. Parametrization.** `@pytest.mark.parametrize` runs one test function once per
input, each a separate result. We generate inputs from the YAML cases — data-driven
testing pays off: add a case, get a test.

**5. Unit vs integration.** Unit = logic in isolation (no sockets). Integration =
real server + real socket + real transport working together (today's file).

**6. Reading a full response from a stream.** No message boundaries over TCP, so
`send()` reads until a final result code (OK/ERROR/+CME ERROR) or a timeout. Send
`ATE0` first so echo doesn't clutter the reply.

**7. Ephemeral port (0) + per-connection isolation.** Binding to port 0 lets the OS
pick a free port (no conflicts, parallel-safe). Each test opens its own connection,
and since modem state is per-connection, each test gets a fresh modem.

### Interview flashcards — Day 8

- **Q: How would you run these tests against a real modem instead of the
  simulator?**
  A: Write one new `Transport` implementation (serial instead of TCP). The driver
  and the test plans don't change — that's why I programmed against a Transport
  interface.

- **Q: What is an abstract base class and why use one for Transport?**
  A: A class that can't be instantiated and forces subclasses to implement its
  methods. It makes "every transport has open/close/send" a rule Python enforces.

- **Q: What's a pytest fixture, and what does yours do?**
  A: Reusable setup/teardown a test depends on. Mine starts the simulator in a
  background thread on an ephemeral port and tears it down after the tests.

- **Q: How does one test function produce a pass/fail per YAML case?**
  A: `@pytest.mark.parametrize` — I feed it every case loaded from the plans, so
  pytest runs the function once per case with its own result line.

- **Q: Unit vs integration test in your project?**
  A: Unit tests call the command logic directly with no sockets; integration tests
  start a real server and drive it over a real socket through the transport.

- **Q: How do you read one complete modem response over TCP?**
  A: Accumulate bytes and stop when a final result code line (OK/ERROR/+CME ERROR)
  appears, bounded by a timeout — because TCP gives a stream with no message
  boundaries.

### Design decisions to be able to defend (Day 8)

- **Transport interface** (dependency inversion) — the hardware-swap seam.
- **In-process server fixture on an ephemeral port** — hermetic, parallel-safe, no
  external process to start.
- **Parametrize over YAML cases** — one readable pass/fail per case.
- **Per-connection isolation** — reuse of the Day 3 state design for free test
  isolation.

---

## Day 9 — Timeouts, retries, backoff, and test doubles

### The concepts

**1. Timeouts (deadline pattern).** Every wait is bounded — a hang blocks the whole
run. We set a deadline (`now + timeout`) and never read past it; on the deadline,
`send()` raises `TimeoutError`.

**2. Retries — double-edged.** They hide *transient* failures (good) but can *mask
real bugs* if used blindly. So we record the attempt count — "passes only on
attempt 4 every time" is a failing case in disguise, and the metric exposes it.

**3. Exponential backoff.** Wait longer before each retry (0.05 → 0.1 → 0.2s).
Hammering a struggling device doesn't help; increasing breathing room does.
Production adds random **jitter** so clients don't retry in lockstep.

**4. Exceptions as control flow.** Normal path returns a response; no-response path
raises `TimeoutError`; the runner catches it and decides to retry.

**5. Test doubles / dependency injection.** Because the runner depends on the
Transport *interface*, tests inject a `FakeTransport` programmed to fail/time out on
cue — deterministic retry tests with no sockets. Stub = canned answers; mock = also
asserts calls; fake = lightweight working substitute (ours).

### Interview flashcards — Day 9

- **Q: How do you keep a test from hanging on a dead device?**
  A: Bounded waits via a deadline — if no complete response arrives in the case's
  timeout, `send()` raises TimeoutError and the case is recorded as timed out.

- **Q: Retries make flaky tests pass — isn't that dangerous?**
  A: It can be. Retries should absorb transient blips, not hide persistent bugs, so
  I record the attempt count. A case that only passes after several retries is
  surfaced as suspect rather than silently green.

- **Q: What is exponential backoff, and why jitter?**
  A: Increasing the wait between retries so you don't hammer a struggling system;
  jitter randomizes the waits so many clients don't retry simultaneously.

- **Q: How did you test retry/timeout logic without a flaky real system?**
  A: I injected a fake transport programmed to time out or fail on specific
  attempts. The runner talks to the Transport interface, so swapping in a fake is
  trivial — dependency injection.

- **Q: Difference between a stub, a mock, and a fake?**
  A: A stub returns canned responses; a mock also verifies how it was called; a fake
  is a lightweight working implementation. My `FakeTransport` is a fake.

### Design decisions to be able to defend (Day 9)

- **Per-case timeout/retries from the plan** — behavior is data-driven config.
- **Raise-and-catch TimeoutError** — clean separation of normal vs no-response
  paths.
- **Record attempts + timed_out** — retries stay honest and feed Day 12
  classification.
- **FakeTransport** — the interface enables deterministic tests of failure paths.

---

## Day 10 — Metrics, JSON summaries, and a CLI

### The concepts

**1. Machine-readable output vs logs.** Logs are for humans reading one run; a JSON
summary is for machines — CI gates on it, dashboards chart it, the Day 14 report is
generated from it. Instrument from the start so numbers never have to be invented.

**2. What we measure.** Cases/passed/failed, pass rate %, per-case latency + total
duration, total retries (flakiness absorbed), timeouts (separated because a
no-response ≠ a wrong-response — the seed of Day 12 classification).

**3. JSON + serialization.** JSON = universal text data format. `json` module +
`dataclasses.asdict()` bridges typed `CaseResult` objects to portable data.

**4. Single-responsibility separation.** runner (one case) → report (aggregate +
write) → run.py (orchestrate/CLI). Each does one job, each testable alone.

**5. CLI with argparse + exit codes.** `argparse` gives flags/help/validation; the
tool returns exit code 0 (all passed) or non-zero (something failed) so CI and
scripts can gate on it.

**6. Don't commit generated artifacts.** `results/summary.json` is output, not
source — gitignore `results/`.

### Interview flashcards — Day 10

- **Q: Why emit a JSON summary instead of just logging?**
  A: Machines consume it — CI can gate on it, a report/dashboard can render it, and
  it's the single source for later reporting. Structured data outlives a scrollback.

- **Q: What metrics do you capture and why?**
  A: Pass/fail counts and pass rate (did it conform), latency/duration
  (performance), retries (flakiness absorbed), and timeouts (a distinct, harsher
  failure). Retries and timeouts specifically set up fault classification.

- **Q: How does your tool tell CI whether the run passed?**
  A: Exit code — 0 if all cases passed, non-zero otherwise. CI reads the exit code
  to pass or fail the build.

- **Q: Why split runner, report, and the CLI into separate files?**
  A: Single responsibility — running a case, aggregating results, and orchestrating
  are different jobs; separating them keeps each testable and replaceable.

- **Q: (Git gotcha) You added a file to `.gitignore` but it still shows in
  `git status` / stayed on GitHub — why?**
  A: `.gitignore` only stops *untracked* files from being staged; it doesn't untrack
  something already committed. To stop tracking it while keeping the local copy:
  `git rm --cached <file>`, then commit. Verify with `git ls-files <path>` (empty =
  untracked).

### Design decisions to be able to defend (Day 10)

- **JSON summary** for machine consumption + a human-readable printout.
- **Exit codes** so the CLI integrates with CI/automation.
- **runner / report / CLI separation** — single responsibility.
- **gitignore generated `results/`** — outputs aren't source.

---

## Day 11 — Coverage, positive/negative testing, independence, DRY

### The concepts

**1. Coverage = breadth.** Exercise every feature area and the meaningful cases in
each, not many variants of one easy path. We spread 21 cases across identity,
registration, PDP, and errors so the pass rate reflects the whole modem.

**2. Positive vs negative testing.** Positive = a valid action gives the right
result; negative = an invalid action *fails correctly* (bad cid → ERROR, attach
before register → ERROR). Conformance leans hard on negative cases — proving a
device rejects what it should.

**3. Test independence.** Each case sets up its own state via `precondition`, so
order doesn't matter and a failure points at one thing. Independent tests can run in
any order / parallel / alone.

**4. DRY (don't repeat yourself).** Extracted the plan-run loop into one
`run_plan()` so there's a single place that knows how to run a plan — fewer places
for bugs to hide or changes to be missed.

### Interview flashcards — Day 11

- **Q: What's the difference between positive and negative testing, and why do
  negative tests matter here?**
  A: Positive checks a valid action succeeds; negative checks an invalid action
  fails the right way. In conformance, proving a device correctly *rejects* bad
  input is often the more important half.

- **Q: How do you keep test cases independent?**
  A: Each case sets up the state it needs in its preconditions, so it doesn't rely
  on run order or leftovers — it can run alone, in any order, or in parallel.

- **Q: How did you decide what to test?**
  A: By feature area (identity, registration, data/PDP, errors) and by covering both
  the happy path and the failure path in each, rather than piling up easy cases.

- **Q: What does DRY mean and where did you apply it?**
  A: Don't repeat yourself — I pulled the duplicated "run every case in a plan" loop
  into a single `run_plan()` function used by the CLI.

- **Q: (We hit this) A test broke because you added a test case — is the test
  wrong?**
  A: No — it was doing its job (a tripwire on the data's shape). But an exact-count
  assertion is *brittle*: it breaks on every legitimate change. Better to assert on
  properties you care about (a lower bound, or that a specific case exists) than a
  hard-coded count.

- **Q: (We hit this) The same test case passed under pytest but failed under the
  live CLI — how is that possible?**
  A: Different connection models. The integration test opens a fresh connection per
  case (isolated state), so an un-registered-modem left by a prior case didn't carry
  over. The CLI reuses one connection per plan, so state carried, and a case that
  wasn't self-sufficient (no precondition to register first) failed. Fix: make the
  case set up its own state. Deeper point: a non-independent test can hide behind an
  isolating runner — and a test failing on its own setup is a *harness* fault, not a
  *device* fault (the Day 12–13 distinction).

### Design decisions to be able to defend (Day 11)

- **Balanced positive + negative cases** across all four feature areas.
- **Self-contained preconditions** for order-independent, isolated tests.
- **`run_plan` extraction** to remove duplication (DRY).

---

## Day 12 — Fault injection

### The concepts

**1. Fault injection / chaos engineering.** Deliberately introduce failures (delays,
corrupt data, drops) to prove your detector detects, not just that the happy path
works. Netflix's Chaos Monkey is the famous example. Here we inject modem faults to
verify the *harness* catches them.

**2. The fault taxonomy.** delay (slow firmware), malformed (corrupted serial data),
dropout (crash/unplug), wrongstate (firmware that lies "OK"). Each mimics a real
modem failure and produces a different observable.

**3. Test hooks/backdoors.** `AT+FAULT` is a simulator-only control command, not real
AT. Keep test hooks obviously separate from production behavior so they're never
mistaken for conformance.

**4. Faults at the boundary.** Applied in `server.py` (delivery layer), not
`commands.py` (the model stays faithful). The fault-setting command is answered
honestly by capturing the mode *before* handling it (same trick as echo).

**5. `conftest.py`.** pytest auto-loads fixtures from `conftest.py` for all test
files — the idiomatic place for shared fixtures (like the server fixture the
integration and fault tests both use).

**6. Sets up classification (Day 13).** Producing faults on demand is what lets the
harness learn to tell a device fault from a timeout from a harness fault.

### Interview flashcards — Day 12

- **Q: What is fault injection and why did you add it?**
  A: Deliberately making the device fail on command, so I can prove the harness
  actually detects failures — you can't trust a detector you've only run on the
  happy path. It's the chaos-engineering idea applied to a modem.

- **Q: What kinds of faults, and why those?**
  A: Delay, malformed response, dropout, and a lying "always-OK" mode — each mirrors
  a real modem failure (slow firmware, corrupted serial, crash, buggy state
  reporting) and each looks different to the harness.

- **Q: `AT+FAULT` isn't a real AT command — is that a problem?**
  A: No — it's a clearly-labeled, simulator-only test hook, kept separate from
  conformance behavior and never used in a real test plan.

- **Q: Why apply faults in the server, not the command logic?**
  A: Faults are about how the response is delivered (late/garbled/dropped/wrong), so
  they belong at the delivery boundary; the command model stays a faithful reference.

- **Q: What is conftest.py?**
  A: A file pytest auto-loads to share fixtures across all test files without
  importing — I put the simulator-server fixture there.

- **Q: (Observed live) You switched fault modes and the switch command itself came
  back corrupted — bug?**
  A: No — the `fault_before` design applies the *currently active* fault to this
  command's outgoing response, and the *new* fault only affects later commands.
  Consequence: to switch cleanly, send `AT+FAULT=none` first. It's the same
  "capture state before handling" rule that keeps echo/fault-set commands faithful.

- **Q: (Debugging lesson) Your code changes didn't take effect — how did you find
  out why?**
  A: Two tells: `pytest` (which starts a fresh in-process server) isolated code
  correctness from a stale long-running server on the port; and the *log format*
  in the output didn't match my latest code, proving the running process was old /
  the file wasn't saved. When behavior ≠ code, first confirm you're running the code
  you think you are.

### Design decisions to be able to defend (Day 12)

- **Fault injection as a labeled, simulator-only hook** (`AT+FAULT`), never in a
  conformance plan.
- **Faults at the server boundary**, command model stays faithful.
- **`fault_before` capture** so the control command answers honestly (mirrors echo).
- **Shared fixture in `conftest.py`** (DRY for test setup).

---

## Day 13 — Fault classification and measuring a classifier

### The concepts

**1. Why classify.** When a conformance test fails, the lab's first question is "is
it the device or our setup?" A harness that separates **device fault** from
**harness fault** is far more useful than one that just says "failed" — it directs
the fix to the right team and preserves trust in the rig.

**2. The four labels + ordered rules.** PASS → HARNESS_FAULT (we recorded an
our-side error) → TIMEOUT (no response in window) → DEVICE_FAULT (reachable but
wrong). Order matters; each check is a clean signal, not a guess.

**3. Our-error vs device-behavior.** The runner now catches non-timeout exceptions
(e.g. connection refused) and records a `harness_error`. `TimeoutError` = the device
didn't answer; a connection error = we couldn't reach it. Same surface, opposite
blame.

**4. Measuring a classifier.** Test it on KNOWN faults (ground truth): inject a
fault, so we know the true label; classify; compute accuracy = correct/total. Same
idea as evaluating any classifier on a labeled set. Turns "I built a classifier"
into "I measured it at X% across N scenarios."

### Interview flashcards — Day 13

- **Q: A conformance test fails — how does your harness decide whose fault it is?**
  A: Rule-based, in order: if we recorded an error on our own side it's a harness
  fault; if there was no response in the window it's a timeout; if the device
  answered but wrong, it's a device fault; otherwise it passed.

- **Q: Why does the device-vs-harness distinction matter?**
  A: It sends the fix to the right place. Blaming the device for a loose cable or a
  bad test script wastes time and erodes trust in the harness.

- **Q: Give a device fault vs a harness fault.**
  A: Device: the modem returns garbage or the wrong registration state. Harness: the
  test can't even connect to the modem, or a bug in my runner throws — that's on us.

- **Q: How do you know your classifier is accurate?**
  A: I run scenarios where I injected the fault myself, so I know the true label,
  then measure how often the classifier agrees — a classification-accuracy number
  over a labeled set.

- **Q: How do you tell a timeout from a device fault?**
  A: A timeout is no response before the deadline (a `TimeoutError`); a device fault
  is a response that arrived but didn't match. Different signals, different labels.

- **Q: (We hit this) A config file silently disappeared from the repo — how did you
  notice and investigate?**
  A: The Docker build context ballooned (100KB → 25MB), which meant `.venv` was
  being copied in — i.e. `.dockerignore` was gone. `git log -- .dockerignore` showed
  it was removed in a commit, because `git add -A` stages *deletions* too: if a file
  vanishes from the working tree, `-A` commits it as removed. Lesson: `-A` is
  convenient but commits removals; and a sudden metric change (build size) is a clue
  worth chasing.

### Design decisions to be able to defend (Day 13)

- **Rule-based classifier with ordered checks** — transparent and defensible.
- **`harness_error` signal** separating our-side errors from device behavior.
- **Accuracy measured on labeled injected faults** (ground truth) — the headline
  metric.
- **Classification folded into the JSON report** (`by_category`) for Day 14's
  rendering.

---

## Day 14 — JUnit XML + HTML reporting

### The concepts

**1. JUnit XML.** The de-facto standard test-report schema (not Java-specific). CI
tools read it to show pass/fail, annotate PRs, and track trends — no knowledge of
your harness needed. Producing a standard format makes the tool interoperable.

**2. HTML report.** The human view: a self-contained page (inline CSS) you can open,
email, or commit. Turns "78 tests pass" into something someone can *see*.

**3. One summary, many renderings.** `build_summary` computes the data once; JSON /
JUnit / HTML only *present* it. Single source of truth, multiple views — change the
metrics once, all views update.

**4. Escaping.** Untrusted text (a modem response) can contain XML/HTML special
characters. ElementTree escapes XML automatically; `html.escape` handles the HTML.
Awareness of escaping is a security-hygiene signal.

### Interview flashcards — Day 14

- **Q: What is JUnit XML and why generate it?**
  A: A standard test-report format CI systems understand. Emitting it lets CI show
  pass/fail, annotate builds, and trend results without knowing my harness's
  internals.

- **Q: You produce JSON, JUnit, and HTML — why three?**
  A: Different audiences: JSON for machines/automation, JUnit for CI, HTML for
  humans. All render the same summary, so there's one source of truth.

- **Q: How do you keep generated HTML/XML safe and valid?**
  A: Escape untrusted content — ElementTree escapes XML for me, and I use
  `html.escape` for the HTML — so a response containing `<`, `&`, or quotes can't
  corrupt the markup.

### Design decisions to be able to defend (Day 14)

- **One summary → three renderings** (JSON/JUnit/HTML): single source of truth.
- **Stdlib only** (`xml.etree`, `html.escape`) — no new dependencies.
- **Category surfaced in both reports** (JUnit `classname`/`type`, HTML badge).

---

## Day 15 — CI/CD, Compose orchestration, and artifacts

### The concepts

**1. CI/CD.** Runs checks automatically on every push. We added an end-to-end
conformance run (real sim + harness + report) on top of pytest, so every commit
answers "does it conform?" and publishes the report.

**2. Multi-container orchestration.** Compose runs simulator + harness together;
the harness reaches the sim by *service name* (`--host simulator`) — the Day 2
name-based networking.

**3. `depends_on` = started, not ready.** It waits for the container to start, not
for the server to accept connections — hence a brief `sleep` (production would use a
health check).

**4. Volumes.** Mount a host folder into the container (`./results:/app/results`) so
generated files survive the container and land on the host.

**5. Artifacts + `if: always()`.** CI saves the `results/` folder as a downloadable
artifact; `if: always()` uploads it even on failure — when you most want the report.

**6. Gating on exit code.** `harness.run` exits 0/1; CI turns a non-zero exit into a
red build, so a real conformance failure fails the pipeline.

### Interview flashcards — Day 15

- **Q: What does your CI pipeline do on every push?**
  A: Installs deps, runs the unit + integration tests, then starts the simulator and
  runs the full conformance pass against it, and uploads the HTML/JUnit report as a
  downloadable artifact. A conformance failure fails the build.

- **Q: In Docker Compose, how does the harness find the simulator?**
  A: By service name over Compose's default network — `--host simulator` resolves to
  the simulator container.

- **Q: Does `depends_on` wait for the simulator to be ready?**
  A: No — only for it to start. "Started" isn't "accepting connections," so I sleep
  briefly (a health check would be the production-grade fix).

- **Q: How do you get the report out of a CI run?**
  A: Upload `results/` as a build artifact with `actions/upload-artifact`, using
  `if: always()` so it's available even when the run fails.

### Design decisions to be able to defend (Day 15)

- **CI runs both pytest and a live end-to-end conformance pass** (fast checks + real
  report).
- **Report published as an artifact** (`if: always()`) — visible without cloning.
- **Compose = full local conformance pass** with a results volume.
- **Build gated on the harness exit code.**

---

## Day 16 — The README as a test plan

### The concepts

**1. Lead with "what it proves."** A reviewer cares first that the project
demonstrates device-vs-harness fault triage with a measured accuracy number — that
belongs at the top, above implementation detail.

**2. Test-plan structure, not a tutorial.** Purpose → architecture → how to run →
command/fault/classification matrices → reports → scope. No narrative walkthrough.

**3. Runnable in one paste + a CI badge.** `docker compose up --build` is the whole
setup; the badge signals "tested and green" at a glance.

**4. Name your limitations and the IP boundary.** Volunteering scope reads as
maturity; stating "public 3GPP TS 27.007 only" removes any confidentiality ambiguity.

### Interview flashcards — Day 16

- **Q: Someone lands on your repo — what do you want them to learn in 60 seconds?**
  A: What it proves (fault triage at 100% accuracy), that it's tested and green in
  CI, and how to run the whole thing with one command.

- **Q: Why call out limitations in your own README?**
  A: It shows I understand the boundaries of my work — a focused model, not a full
  3GPP stack — which builds credibility rather than undermining it.

### Design decisions to be able to defend (Day 16)

- **README leads with impact + a measured metric**, not implementation.
- **One-command quick start** (Docker) so anyone can reproduce it.
- **Explicit scope + public-spec IP note.**

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

*Appended per day. Next up (Day 17): the finale — the real-hardware bridge decision
(Tier A/B/C), a fault-injection demo (GIF/asciinema), and freezing the final metrics
that become the resume bullets.*
