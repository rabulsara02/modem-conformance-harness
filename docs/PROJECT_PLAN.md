# Modem Simulator + Conformance Harness — Project Plan

**Owner:** Rahul
**Window:** 17 days (~3–4 hrs/day)
**Last updated:** 2026-07-23

---

## 1. Why this project exists

This is not a portfolio toy. It is a 2-week proof that you live in a specific,
underdefended seam of the job market: **people who understand RF/cellular
concepts AND write real test software.** Software engineers don't understand
modems; RF engineers write mediocre Python. The overlap is thinly populated and
directly hireable.

Your SGS conformance-testing experience is the credential here, not a costume.
Everything you build should read like a description of your day job.

### What we are targeting
- **Titles to aim the resume at:** Test Automation Engineer, Validation Engineer,
  Test Development Engineer, Systems Test Engineer, Hardware Test Software
  Engineer, DV Engineer.
- **Titles to avoid:** "RF Engineer" (you don't clear the 5-yr EE bar) and
  generic "Software Engineer" (206:1 applicant pool).
- **Geography advantage:** Bay Area labs (Apple, NVIDIA, Qualcomm, Supermicro)
  run exactly these test roles onsite/hybrid.

### The one feature that makes it not a toy
**Fault injection + fault classification.** The simulator can deliberately
misbehave; the harness must tell a *device* failure apart from a *harness*
failure. That distinction is the exact thing validation hiring managers screen
for, and it maps straight onto your rewritten SGS bullet.

---

## 2. Guardrails (read before every work session)

These are the rules that keep a 2.5-week project from becoming a 6-week one.

1. **The simulator is scaffolding, not the product.** Cap it hard. Resist making
   it good. Every hour spent polishing the simulator is an hour stolen from the
   part that actually sells you.
2. **Protect the fault-classification block (Days 12–14) at all costs.** If
   something has to be cut, cut simulator features — never classification.
3. **Instrument from commit #1.** Log run duration, pass/fail counts, retry
   counts, and classification accuracy from the very first working version.
   Otherwise you finish with a working tool and *no numbers* — the exact
   retrofitting trap you're already in on your current resume.
4. **De-risk the unknowns first (Docker + CI on Days 1–2), before touching the
   real code.** Learning infra while debugging a socket server is how timelines
   explode.
5. **Public AT commands only — no confidentiality risk.** Everything modeled comes
   from public 3GPP TS 27.007 (and related public specs). No SGS client test plans
   or device-specific behavior appear anywhere. This is settled: build freely from
   any publicly documented AT command.
6. **Document everything as you write it (learning-first rule).** Every file gets a
   top-of-file docstring saying what it is and why it exists; every non-obvious line
   gets a plain-English comment. The goal isn't just clean code — it's that Rahul
   can explain any part of this repo to an interviewer from scratch. Write comments
   that teach the "why," not just restate the "what." This applies to every file
   from Day 2 onward.
7. **Teach the background BEFORE each new component (standing request).** Rahul is
   learning bottom-up so he can explain everything he built. Before he writes a file
   that introduces new concepts (sockets, threading, YAML, pytest fixtures, state
   machines, etc.), give a plain-English background primer on the concepts in it —
   tied to the specific lines he's about to write. Don't wait to be asked. Capture
   each primer in `LEARNING_NOTES.md` (concepts + interview flashcards + design
   decisions to defend), and keep adding interview questions and study tips as we go.

---

## 3. Tech stack (locked — do not shop for alternatives mid-project)

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | Your existing scripting language |
| Simulator transport | TCP sockets (`socketserver` or `asyncio`) | Emulates modem serial-over-TCP |
| Test framework | pytest | You've used it; CI-ready |
| Test-plan format | YAML | Declarative, human-readable test cases |
| Reporting | JUnit XML + HTML report | JUnit is the CI standard; HTML for humans |
| CI | GitHub Actions | Runs pytest on push, publishes report |
| Containerization | Docker + docker-compose | Simulator + harness as two services |
| Logging | Python `logging`, structured (JSON option) | Feeds the metrics |

**AT commands to support (cap ~14):** `AT`, `ATE0`, `ATE1`, `AT+CPIN?`,
`AT+CGMI`, `AT+CGMM`, `AT+CIMI`, `AT+CGDCONT`, `AT+CREG`, `AT+CSQ`, `AT+COPS`,
`AT+CFUN`, `AT+CGATT`, `AT+CMEE`. All defined in public 3GPP TS 27.007. `AT+CPIN?`
(SIM ready-state check) and `ATE0`/`ATE1` (echo off/on) are core to a realistic
init sequence. All fully public — no restrictions. Still cap the list here; more
commands is scope creep, not credibility.

---

## 4. Architecture (the mental model)

```
  YAML test plans ──▶  pytest harness  ──▶  TCP  ──▶  Modem Simulator
   (declarative)        │  - driver              (AT parser +
                        │  - timeout/retry         registration
                        │  - classifier            state machine +
                        │  - logger                fault-injection mode)
                        ▼
              JUnit XML + HTML report
              (pass/fail + fault category + metrics)
                        │
                        ▼
              GitHub Actions (runs on push)
```

- **Simulator** speaks AT commands over TCP and holds a **registration state
  machine** (e.g. not-registered → searching → registered → roaming). It has a
  normal mode and a **fault-injection mode**.
- **Harness** reads YAML test plans, drives the simulator, enforces timeouts and
  retries, and — crucially — **classifies every failure** as device fault,
  harness fault, or timeout.

---

## 5. Day-by-day timeline

> Time budget assumes ~3–4 focused hrs/day. Each day lists a **goal**, **tasks**,
> and a **done-when** check. Don't start a phase until the previous "done-when"
> is true.

### Phase 0 — De-risk infrastructure (Days 1–2)
**Do NOT touch the real project code yet.**

**Day 1 — Repo + CI skeleton**
- Create the GitHub repo (`modem-conformance-harness`). Add `.gitignore`,
  `README.md` stub, MIT license.
- Write a trivial `hello.py` and one trivial `test_hello.py`.
- Stand up a GitHub Actions workflow that installs Python, runs `pytest` on
  every push, and shows green.
- **Done when:** a push to `main` triggers a green CI run you can see in the
  Actions tab.

**Day 2 — Docker + Compose skeleton**
- Write a `Dockerfile` that containerizes the hello-world app.
- Write a `docker-compose.yml` with two placeholder services (`simulator`,
  `harness`) that can start and talk over a network.
- Confirm the two containers can reach each other (a `ping` or trivial socket
  echo is enough).
- **Done when:** `docker-compose up` starts both services and they can connect.

*Buffer note: if CI/Docker eats into Day 3, that's fine — this phase is the most
likely to overrun and the whole point of front-loading it.*

---

### Phase 1 — Modem Simulator (Days 3–6)
Scaffolding. Cap it. Move on.

**Day 3 — TCP server + AT echo**
- Build the TCP server that accepts a connection and reads line-terminated AT
  commands.
- Implement `AT` → `OK` and `ATE0`/`ATE1` (echo off/on — actually toggle echo
  behavior, don't just ack). Return `ERROR` for anything unknown.
- Add structured logging (timestamp, command in, response out, latency).
- **Done when:** you can `telnet`/`nc` in, type `AT`, and get `OK`.

**Day 4 — AT command parser + identity commands**
- Build a clean command-dispatch layer (map command → handler).
- Implement identity/info commands: `AT+CGMI`, `AT+CGMM`, `AT+CIMI`, `AT+CSQ`.
- Implement `AT+CPIN?` (SIM ready-state: `READY` / `SIM PIN` / not-inserted) —
  this gates registration, so wire its result into the state machine on Day 5.
- **Done when:** identity commands return spec-shaped responses and `AT+CPIN?`
  reports a settable SIM state.

**Day 5 — Registration state machine**
- Implement states: `SIM_NOT_READY → NOT_REGISTERED → SEARCHING → REGISTERED →
  ROAMING`, plus `DENIED`. Registration is blocked until `AT+CPIN?` reports
  `READY`.
- Implement `AT+CREG`, `AT+CGATT`, `AT+COPS`, `AT+CFUN` so they read/drive state.
- Model realistic transitions (e.g. `CFUN=0` deregisters; SIM-not-ready blocks
  attach).
- **Done when:** a scripted sequence walks the modem through all states and
  `AT+CREG?` reports them correctly.

**Day 6 — PDP context + hardening + freeze**
- Implement `AT+CGDCONT` (define PDP context) and `AT+CMEE` (error verbosity).
- Handle malformed input gracefully (return `ERROR`, don't crash).
- **FREEZE the simulator feature set here.** Write down the final command list in
  the README. From now on the simulator only changes to add fault-injection.
- **Done when:** ~12 commands work, server survives garbage input, command list
  documented.

---

### Phase 2 — Conformance Harness (Days 7–11)
This is where the product starts.

**Day 7 — YAML test-plan schema**
- Design the test-case schema: `name`, `send` (command), `expect` (regex/exact),
  `timeout_ms`, `retries`, optional `precondition` (state to set first).
- Write 3–4 example test plans as YAML files.
- **Done when:** the schema is documented and a sample plan parses without error.

**Day 8 — pytest driver reading YAML (via a transport interface)**
- **Build against a `Transport` abstraction, not a raw socket.** Define a small
  interface (`send(cmd) -> response`, `open()`, `close()`) with a `TcpTransport`
  implementation for the simulator. Because real hardware is committed (Day 17),
  a future `SerialTransport` (`/dev/ttyUSB`) must drop in with zero harness
  changes. This is the single most important design decision in the harness —
  get it right now, cheaply.
- Write a pytest fixture that opens the transport to the simulator.
- Use pytest parametrization to generate one test per YAML case.
- Assert responses against `expect`.
- **Done when:** `pytest` runs YAML-defined cases through the transport interface
  and reports pass/fail per case.

**Day 9 — Timeout + retry logic**
- Add per-case timeout enforcement (fail the case if no response in time).
- Add retry logic with backoff; record retry counts.
- **Done when:** a deliberately slow command times out cleanly and a flaky one
  retries and records the count.

**Day 10 — Structured logging + metrics capture**
- Emit per-run metrics: total cases, pass/fail counts, total duration, per-case
  latency, retry counts. Write them to a JSON summary file.
- **Done when:** every run produces a machine-readable metrics summary.

**Day 11 — Expand coverage to ~20 cases + cleanup**
- Grow the YAML suite to ~20 test cases covering identity, registration
  transitions, PDP context, and error handling.
- Refactor/clean the harness; add docstrings.
- **Done when:** ~20 cases run green against the healthy simulator.

---

### Phase 3 — Reporting + Fault Classification (Days 12–14)
**Highest-value block. Protect it. Do not let earlier phases bleed into it.**

**Day 12 — Fault injection in the simulator**
- Add a fault-injection mode toggled by config/env: delayed responses, malformed
  replies, intermittent dropouts, wrong-state responses.
- **Done when:** you can start the simulator in "misbehave" mode and observe each
  fault type.

**Day 13 — Fault classifier in the harness**
- On every failure, classify the cause: **device fault** (bad response from a
  reachable modem), **harness fault** (our own bug/timeout-config issue), or
  **timeout** (no response in window).
- Record classification accuracy: run known-fault scenarios and check the
  classifier labels them correctly.
- **Done when:** injected faults are labeled with a measurable accuracy number.

**Day 14 — JUnit XML + HTML report**
- Emit JUnit XML (CI-consumable) and a human HTML report showing pass/fail,
  fault category per failure, and the run metrics.
- **Done when:** one command produces both reports and the HTML shows fault
  categories.

---

### Phase 4 — Integration, CI, polish (Days 15–17)

**Day 15 — Wire everything into CI + Compose**
- Update `docker-compose.yml` so CI spins up the simulator, runs the harness
  against it, and collects reports.
- Update GitHub Actions to publish the JUnit results and upload the HTML report
  as an artifact.
- **Done when:** a push runs the full suite in CI and the report is downloadable
  from the Actions run.

**Day 16 — README as a test plan**
- Write the README so it reads like a **test plan**, not a tutorial: purpose,
  architecture diagram, how to run, the command list, the fault-injection
  matrix, and the metrics the harness reports.
- Note that the model is built entirely from public 3GPP TS 27.007 — safe to
  discuss openly in interviews.
- **Done when:** a stranger can clone, `docker-compose up`, and understand what
  the tool proves in under 5 minutes.

**Day 17 — Fault-injection demo + final metrics**
- Record a short demo (asciinema/GIF or a scripted run) showing normal pass, then
  fault-injection producing classified failures.
- Freeze the final metrics: case count, pass rate, classification accuracy, avg
  run duration, retry stats. These become the resume numbers.
- **Real-hardware bridge (decided: yes; depth TBD).** Reserve this slot to point
  the harness at a real `$20` USB LTE modem over its serial/`/dev/ttyUSB` port
  instead of the TCP simulator. See Section 9 for the depth decision to make when
  we get here.
- **Done when:** demo captured, metrics table finalized in the README.

---

## 6. Metrics to instrument (from Day 1, not retrofitted)

Capture these in the JSON summary and surface them in the HTML report:

- Total test cases and pass/fail counts
- Total run duration and per-case latency
- Retry counts (per case and total)
- **Fault-classification accuracy** (the headline number)
- Number of AT commands supported and states modeled

These are what turn into quantified resume bullets. If you can't put a number on
it at the end, the instrumentation failed.

---

## 7. Definition of done (the whole project)

- [ ] Public GitHub repo, green CI on `main`
- [ ] Simulator: ~12 AT commands + registration state machine + fault-injection
- [ ] Harness: YAML-driven, ~20 cases, timeout/retry, fault classifier
- [ ] JUnit XML + HTML report with fault categories
- [ ] `docker-compose up` runs the full suite end-to-end
- [ ] CI publishes results + report artifact
- [ ] README reads like a test plan; IP line drawn to public specs only
- [ ] Final metrics table with classification accuracy
- [ ] Demo (GIF/asciinema) of fault injection → classified failures

---

## 8. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Docker/CI overruns Phase 0 | High | Front-loaded to Days 1–2; buffer into Day 3 |
| Simulator gold-plating steals time | High | Hard freeze on Day 6; it's scaffolding |
| Fault-classification block gets squeezed | Med | Cut simulator features first, never Days 12–14 |
| No quantifiable metrics at the end | Med | Instrument from commit #1 (Section 6) |
| Real-hardware bridge blows timeline | Med | Transport interface built Day 8; hardware confined to Day 17; depth decided when we get there (Section 9) |
| USB modem quirks (drivers, AT dialect) | Med | Pick a well-documented module; keep the simulator as the guaranteed-green baseline so hardware is additive, never blocking |

---

## 9. Real-hardware bridge (committed — decide depth on Day 15)

Decision made: **yes, we validate against a real modem.** The `Transport`
abstraction (Day 8) is what makes this cheap. What's still open is *how deep* to
go — decide on Day 15 based on how much slack remains:

- **Tier A — Smoke bridge (~half a day).** Run the existing suite against a real
  USB modem over serial for identity/SIM/signal commands only. Resume line:
  "validated the harness against real hardware." Lowest risk.
- **Tier B — Real registration (~1–1.5 days).** Drive an actual network
  attach/registration sequence on live hardware and reconcile it against the
  simulator's state machine. Stronger, but exposes you to real-world timing and
  carrier quirks.
- **Tier C — Hardware fault comparison (~2–3 days).** Compare fault behavior of
  real hardware against injected simulator faults. Highest credibility, highest
  timeline risk — only if you're well ahead.

**Rules:** the simulator stays the guaranteed-green baseline in CI; hardware is
always additive and never blocks the pipeline. Buy a well-documented USB LTE
module (Quectel/SIMCom-class) early so drivers aren't a Day-17 surprise.

### Other stretch (only if ahead)
- **Written scoping doc** alongside the repo. Not needed for validation roles,
  but it's the near-zero-cost artifact that keeps an FDE-style door open.

---

## 10. Decisions locked (resolved 2026-07-23)

1. **AT command scope — RESOLVED.** All publicly documented AT commands are fair
   game (public 3GPP TS 27.007, no restrictions). Command list includes `AT`,
   `ATE0`/`ATE1`, `AT+CPIN?`, `AT+CIMI`, `AT+CGDCONT`, and the rest of Section 3.
2. **Real hardware — RESOLVED (yes), depth TBD.** We build the transport
   abstraction on Day 8 and bridge to a real USB LTE modem on Day 17. How deep
   (Tier A/B/C) is decided on Day 15 based on remaining slack (Section 9).
3. **Portfolio website — RESOLVED.** Cut it. This project replaces the website in
   the Projects section of the resume.

*All Day-1 blockers cleared — the plan is ready to execute.*

---

*Follow the "done-when" gates in order. When a day's gate isn't met, roll the
remainder forward and cut simulator scope — never the fault-classification work.*
