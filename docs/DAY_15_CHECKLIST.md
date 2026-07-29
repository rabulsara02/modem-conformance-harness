# Day 15 Checklist — Wire it into CI + Docker Compose (automated conformance)

**Goal for today:** make the whole pipeline run itself. Update **Docker Compose** so
`docker compose up` runs a full conformance pass (simulator + harness together), and
update **GitHub Actions** so every push starts the simulator, runs the harness
against it, and uploads the HTML report as a downloadable **build artifact**. After
today, "does the modem conform?" is answered automatically on every commit.

**Time:** ~2.5 hours (mostly config — YAML, not Python). **Prereqs:** Day 14 done,
81 tests, CI green.

> Code blocks start at the left margin. No code changes — just `docker-compose.yml`
> and the CI workflow.

---

## Background knowledge (read before you build)

### 1. What CI/CD actually does for you

**CI (continuous integration)** runs your checks automatically on every push, so
problems surface immediately instead of at review time. You already run `pytest` in
CI; today you add a full **end-to-end conformance run** (real simulator, real
harness, real report) and make that report downloadable. The payoff: anyone can open
a build and see "21/21 cases passed" plus the report, without cloning anything.

### 2. Multi-container orchestration (Compose)

`docker compose` runs several containers as one system. Today's compose file has two
services — `simulator` and `harness` — on a shared network. The harness reaches the
simulator **by service name** (`--host simulator`), exactly the name-based networking
you first saw on Day 2. This is how real systems wire services together.

### 3. `depends_on` starts, it doesn't wait for "ready" (Day 2, again)

`depends_on: [simulator]` makes Compose *start* the simulator first — but "started"
isn't "ready to accept connections." That's the same gotcha from Day 2, so the
harness still `sleep`s briefly before connecting. (A production setup would use a
health check instead of a sleep; worth naming that you know the difference.)

### 4. Volumes — getting files out of a container

A container's filesystem is normally thrown away when it stops. A **volume** mounts a
host folder into the container so files written there persist on your machine. We
mount `./results` so the reports the harness writes inside the container land in your
real `results/` folder.

### 5. CI artifacts + `if: always()`

A **build artifact** is a file CI saves from a run for you to download — here, the
`results/` folder with the HTML/JUnit/JSON reports. We upload it with
`if: always()` so you get the report **even when the conformance run fails** — which
is exactly when you most want to see it.

### 6. Gating the build on conformance

`python -m harness.run` returns exit code 0 (all passed) or 1 (something failed). CI
treats a non-zero exit as a failed step, so a real conformance failure turns the
build red. Your test *rig* and the *device* verdict now both gate the pipeline.

---

## Part A — Compose runs a full conformance pass

Replace `docker-compose.yml` with a two-service version:

```yaml
# docker-compose.yml — run a full conformance pass: the simulator plus the harness.
# `docker compose up --build` starts the simulator, then the harness runs every plan
# against it and writes the reports into ./results on the host.
services:
  simulator:
    build: .
    command: python -m simulator.server
    ports:
      - "5050:5050"

  harness:
    build: .
    # depends_on only waits for the container to START, not for the server to be
    # READY to accept connections — so we sleep briefly first (same lesson as Day 2).
    command: sh -c "sleep 2 && python -m harness.run --host simulator --port 5050"
    depends_on:
      - simulator
    volumes:
      - ./results:/app/results    # generated reports land on the host
```

- [ ] `docker-compose.yml` updated to two services with the `./results` volume.

---

## Part B — Run the full pass locally

```bash
docker compose up --build
```

- ✅ *Worked when:* in the logs, the `harness` service prints the
  `=== Conformance summary ===` line (`cases=21 passed=21 ... pass_rate=100.0%`) and
  then exits, while `simulator` keeps running.
- [ ] Confirm the reports landed on your host: `ls results/` shows
      `summary.json`, `junit.xml`, `report.html`. Open `results/report.html`.
- [ ] Stop it: `Ctrl+C`, then `docker compose down`.

If the harness logs `ConnectionRefusedError`, the simulator wasn't ready in time —
bump the `sleep 2` to `sleep 3` (the readiness-vs-started gotcha).

---

## Part C — CI runs the conformance pass + uploads the report

Replace `.github/workflows/ci.yml` with:

```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -r requirements.txt

      - name: Unit + integration tests
        run: pytest

      - name: Conformance run (harness vs live simulator)
        run: |
          python -m simulator.server &   # start the simulator in the background
          sleep 2                        # give it a moment to bind (started != ready)
          python -m harness.run          # runs all plans; exit code gates the build

      - name: Upload conformance report
        if: always()                     # upload even if the conformance run failed
        uses: actions/upload-artifact@v4
        with:
          name: conformance-report
          path: results/
```

- [ ] `.github/workflows/ci.yml` updated with the conformance run + artifact upload.

---

## Part D — Push and verify the automated pipeline

```bash
git add -A
git commit -m "Day 15: CI runs conformance vs live simulator + uploads report artifact; compose runs full pass"
git push
```

- [ ] On GitHub → **Actions** tab → open your latest run. You should see the
      **Unit + integration tests** step and the **Conformance run** step both green.
- [ ] On that run's summary page, find the **Artifacts** section and download
      `conformance-report`. Unzip it and open `report.html` — the report generated by
      CI, not your laptop.

- ✅ **DAY 15 IS DONE when:** a push turns CI green through both the pytest step and
  the live conformance step, and the `conformance-report` artifact is downloadable
  from the Actions run.

---

## If something breaks

- **CI conformance step fails with `ConnectionRefusedError`:** the background
  simulator needs a moment — increase `sleep 2` to `sleep 3` in the workflow.
- **`docker compose up` harness can't resolve `simulator`:** the `--host` must match
  the service name exactly (`simulator`), and both services must be in the same
  compose file (same default network).
- **`results/` empty on the host after compose:** the `volumes: ./results:/app/results`
  line must be present on the `harness` service; the folder is created if missing.
- **Artifact not showing in CI:** confirm `actions/upload-artifact@v4` and that
  `path: results/` matches where `harness.run` writes (its default `--out`/`--junit`/
  `--html` all live under `results/`).
- **CI red because a case failed:** that's the pipeline working — open the artifact's
  `report.html` to see which case and its fault category. (Make sure you deleted any
  temporary fault-demo case from Day 14.)

---

## Progress log (updated as we go)

*(Fill in as you work through today.)*

---

*When CI runs the conformance pass and publishes the report, Day 15 is done — the
pipeline is fully automated. Day 16 rewrites the README so the repo reads like a test
plan: what it proves, the architecture, how to run it, and the metrics — the first
thing anyone (or a hiring manager) sees.*
