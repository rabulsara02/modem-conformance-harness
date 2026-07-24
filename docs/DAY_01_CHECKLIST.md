# Day 1 Checklist — Make an empty project that tests itself

**Goal for today:** an empty project on GitHub where, every time you save your
work, a robot automatically runs a test and shows a green checkmark. Nothing
"real" is built today — you're proving the pipeline works before it matters.

**Time:** ~2–3 hours, mostly first-time setup.
**You already have:** GitHub account, Python. **Still need:** Docker (but NOT for
today — see the last section; kick off the download in the background).

Work top to bottom. Don't skip. Each step says what to do and how to know it
worked.

---

## Progress log (updated as we go)

**Status: ~90% done — one thing left to confirm (the CI green checkmark).**

What actually happened, and where it differed from the plan:

- **Parts A–B done.** Repo created and cloned. *Deviation:* cloned over **SSH**
  (`git@github.com:rabulsara02/...`) instead of HTTPS. Good thing — SSH auth is
  already set up, so the "password rejected" troubleshooting note doesn't apply
  to you.
- **Part C done.** Virtual env active (`.venv`), pytest installed. *Note:* you're
  on **Python 3.13.1** locally, so we set CI to `3.13` (not the `3.11` the plan
  originally suggested) to keep local and CI matched.
- **Part D done.** `hello.py` + `test_hello.py` created in the editor;
  `pytest` → `1 passed`.
- **Part E–F:** `ci.yml` written and pushed — **confirm the green checkmark in
  the Actions tab to close out Day 1.**
- **Docker (Day 2 prereq) — DONE EARLY.** `docker --version` → 29.6.2 and
  `docker run hello-world` printed "Hello from Docker!" (arm64/Apple Silicon).
  Day 2 has no install step now.

---

## Part A — Create the project (on GitHub, in the browser)

- [ ] **1. Make a new repository.** Go to github.com, click the **+** (top right)
      → **New repository**.
    - Name: `modem-conformance-harness`
    - Description: `Cellular modem simulator + conformance test harness`
    - Visibility: **Public** (employers need to see it)
    - Check **Add a README file**
    - Add `.gitignore` → choose the **Python** template from the dropdown
    - License → choose **MIT License**
    - Click **Create repository**
    - ✅ *Worked when:* you're looking at your new repo page with a README, a
      `.gitignore`, and a `LICENSE` file already in it.

---

## Part B — Get it onto your computer

- [ ] **2. Copy the repo's address.** On the repo page click the green **Code**
      button → **HTTPS** tab → copy the URL (ends in `.git`).

- [ ] **3. Clone it.** Open Terminal, go to wherever you keep projects, and pull
      the repo down. Replace the URL with the one you copied:
    ```bash
    cd ~/projects        # or wherever you want it to live
    git clone https://github.com/<your-username>/modem-conformance-harness.git
    cd modem-conformance-harness
    ```
    - ✅ *Worked when:* `ls` shows `README.md`, `LICENSE`, `.gitignore`.

---

## Part C — Set up Python the clean way

- [ ] **4. Create a virtual environment.** This keeps this project's packages
      separate from everything else on your machine.
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
    - ✅ *Worked when:* your Terminal prompt now starts with `(.venv)`.

- [ ] **5. Install pytest** (the tool that runs tests):
    ```bash
    pip install pytest
    pip freeze > requirements.txt
    ```
    - ✅ *Worked when:* `requirements.txt` exists and contains a `pytest==...`
      line.

---

## Part D — Write a throwaway app + test

This is deliberately trivial. You're testing the *pipeline*, not modem logic.

- [ ] **6. Create the app file `hello.py`:**
    ```python
    def add(a, b):
        return a + b
    ```

- [ ] **7. Create the test file `test_hello.py`:**
    ```python
    from hello import add

    def test_add():
        assert add(1, 1) == 2
    ```

- [ ] **8. Run the test locally:**
    ```bash
    pytest
    ```
    - ✅ *Worked when:* you see green text ending in something like
      `1 passed in 0.01s`.

---

## Part E — Make the robot run the test automatically (this is the real goal)

"GitHub Actions" is the robot. It reads a settings file in your repo and runs
whatever you tell it every time you push code.

- [ ] **9. Create the folders and workflow file.**
    ```bash
    mkdir -p .github/workflows
    ```
    Then create `.github/workflows/ci.yml` with this content:
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
              python-version: "3.11"
          - run: pip install -r requirements.txt
          - run: pytest
    ```
    - ✅ *Worked when:* the file exists at
      `.github/workflows/ci.yml` and the indentation matches exactly (YAML is
      picky about spaces — use 2 spaces, never tabs).

---

## Part F — Push it and watch the checkmark

- [ ] **10. Save your work to GitHub:**
    ```bash
    git add .
    git commit -m "Day 1: CI skeleton with hello-world test"
    git push
    ```

- [ ] **11. Watch the robot run.** On your repo page, click the **Actions** tab.
      You'll see your commit with a spinning yellow dot, then (after ~30–60s) a
      green checkmark.
    - ✅ **TODAY IS DONE when:** the Actions tab shows a green checkmark for your
      push. That means: you save code → a robot runs your tests automatically →
      it passes. The foundation is live.

---

## Background task — start the Docker download now (for Day 2, not today)

Docker Desktop is a big download and you don't want to wait on it tomorrow. Kick
it off while you do Day 1:

- [x] ~~Download + install Docker Desktop for Mac.~~ **DONE.**
- [x] ~~Confirm it's ready.~~ **DONE** — `docker --version` → 29.6.2,
      `docker run hello-world` → "Hello from Docker!" (arm64/Apple Silicon).
      Day 2 can skip installation entirely.

---

## If something breaks

- **`pytest` says "command not found":** your virtual environment isn't active.
  Re-run `source .venv/bin/activate` (prompt should show `(.venv)`).
- **`git push` asks for a password and rejects it:** GitHub needs a Personal
  Access Token, not your account password. Create one under GitHub → Settings →
  Developer settings → Personal access tokens, and paste it as the password. (Or
  set up the GitHub CLI `gh` and run `gh auth login`.)
- **Actions tab shows a red X:** click into the failed run, read the last few red
  lines — it's almost always a YAML indentation error in `ci.yml` or a missing
  `requirements.txt`. Fix, commit, push again.

---

*When the green checkmark appears, you're done for Day 1. Tomorrow (Day 2) is
Docker: putting this in a box and getting two boxes to talk.*
