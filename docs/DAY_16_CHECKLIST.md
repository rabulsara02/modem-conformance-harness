# Day 16 Checklist — README that reads like a test plan

**Goal for today:** write the README so a stranger can understand what the project
*proves*, how to run it, and what it covers — in under five minutes. This is the
single most-read file in the repo and often the only thing a hiring manager opens, so
it's worth getting right.

**Time:** ~1.5 hours (writing + review). **Prereqs:** Day 15 done, pipeline
automated, CI green.

> A full README has been drafted directly into `README.md`. Today is about
> reviewing it, personalizing a couple of things, and confirming the quick-start
> actually works.

---

## Background: what makes a README good (for this kind of project)

- **Lead with the "what it proves," not the "what it is."** A hiring manager cares
  that it demonstrates device-vs-harness fault triage with a measured accuracy
  number — that goes near the top, before implementation detail.
- **Read like a test plan, not a tutorial.** Sections a reviewer expects: purpose,
  architecture, how to run, the command/fault/classification matrices, reports, and
  scope/limitations. No narrative walkthrough.
- **Make it runnable in one paste.** `docker compose up --build` should be all
  someone needs — no environment wrangling.
- **A CI status badge** signals "this is tested and green" at a glance.
- **Name your limitations.** Volunteering scope (it's ~14 commands, deterministic
  registration, invented identity values) reads as maturity, not weakness.
- **State the IP boundary.** Everything is built from **public 3GPP TS 27.007** — no
  confidential or device-specific behavior. Say it plainly so there's no ambiguity.

---

## Part A — Review the drafted README

- [ ] Open `README.md` in a Markdown preview (VS Code: **Cmd+Shift+V**).
- [ ] Confirm the tables (commands, faults, classification) and the ASCII
      architecture diagram render cleanly.
- [ ] Read the **What this proves** and **Scope & limitations** sections and make
      sure you'd say every sentence out loud in an interview. Tweak any wording that
      isn't in your voice.

## Part B — Personalize + fact-check

- [ ] **CI badge:** the URL uses your GitHub path
      (`rabulsara02/modem-conformance-harness`). Confirm it matches your repo; the
      badge renders live once pushed.
- [ ] **Numbers:** the README cites 81 tests, 21 conformance cases, ~14 AT commands,
      4 fault modes, and 100% (6/6) classification accuracy. Confirm these still match
      (`pytest` count, `python -m harness.run` case count, `python -m harness.selfcheck`).

## Part C — Prove the quick-start works from scratch

The worst README bug is a quick-start that doesn't run. Verify the headline command
on a clean checkout of the state:

- [ ] `docker compose up --build` → the harness prints the conformance summary and
      writes `results/report.html`. `Ctrl+C`, then `docker compose down`.
- [ ] (Optional, most thorough) clone the repo into a fresh temp folder and run the
      Docker quick-start there, to confirm nothing depends on your local setup.

## Part D — Commit + push

```bash
git add -A
git commit -m "Day 16: README that reads like a test plan (purpose, architecture, matrices, scope, IP)"
git push
```

- [ ] On GitHub, confirm the README renders on the repo home page and the CI badge
      shows green.

- ✅ **DAY 16 IS DONE when:** the repo front page tells the whole story — what it
  proves, how to run it, and what it covers — and the CI badge is green.

---

## If something looks off

- **Badge shows "unknown" / broken:** the path must exactly match
  `<user>/<repo>` and the workflow file is `ci.yml`. It can take one push/run to
  populate.
- **Tables not rendering:** GitHub needs a blank line before a table and `|`-delimited
  rows; the preview will show this immediately.
- **Diagram looks misaligned:** it's inside a fenced code block (monospace) on
  purpose — check the triple backticks around it survived any edit.

---

## Progress log (updated as we go)

- ✅ **DAY 16 COMPLETE.** Rewrote the README as a test plan: what it proves (fault
  triage + 100% accuracy), architecture, one-command quick start, command/fault/
  classification matrices, reports, scope, and the public-spec IP note. CI badge live.
- **Diagram polish:** replaced the ASCII architecture drawing with a **Mermaid**
  flowchart (GitHub renders it natively) and the jammed layout with a clean annotated
  **directory tree** — matching each representation to the kind of info (flow vs
  hierarchy).

---

*When the README tells the whole story and CI is green, Day 16 is done. Day 17 is the
finale: the real-hardware bridge decision (Tier A/B/C from the plan), a
fault-injection demo (GIF/asciinema), and freezing the final metrics — the numbers
that become your resume bullets.*
