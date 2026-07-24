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

*Appended per day. Next up (Day 5): the registration state machine — how a modem
moves from "SIM not ready" to "searching" to "registered," and the AT commands
(CFUN, CGATT, COPS, CREG) that drive and report it.*
