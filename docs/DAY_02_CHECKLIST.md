# Day 2 Checklist — Put it in a box, and get two boxes talking

**Goal for today:** wrap your hello-world app in a Docker "box" (container), then
run **two** boxes that can talk to each other over a network. Still nothing
"real" inside — you're proving the two-container setup works, because on the real
project one box is the fake modem and the other is the tester.

**Plain-English why:** later, your simulator and your test harness run as two
separate programs that talk over TCP. Today you build that two-program skeleton
with placeholders, so when the real code arrives it just slots in.

**Time:** ~2 hours. **Prereq:** Docker installed — ✅ already done on Day 1
(v29.6.2, arm64). No install step today.

Work top to bottom. Each step has a "worked when" check.

---

## Part A — One box: containerize the hello-world app

A "Dockerfile" is a recipe that tells Docker how to build your box.

- [x] **1. Create a file named `Dockerfile`** (no extension) in the repo root:
      ✅ DONE. *(Hiccup: first build failed with "Dockerfile cannot be empty" —
      the file was saved before the content was pasted. Filled it in and rebuilt
      fine.)*
    ```dockerfile
    FROM python:3.13-slim
    WORKDIR /app
    COPY requirements.txt .
    RUN pip install -r requirements.txt
    COPY . .
    CMD ["pytest"]
    ```
    - *What each line does:* start from a small Python image → set the working
      folder → copy in the dependency list and install it → copy the rest of your
      code → when the box runs, run `pytest`.

- [x] **2. Build the box:** ✅ DONE — built clean, ending in
      `naming to docker.io/library/modem-harness:latest`.
    ```bash
    docker build -t modem-harness .
    ```

- [x] **3. Run the box:** ✅ DONE — ran inside the container (`platform linux`,
      `rootdir: /app`) → `1 passed`.
    ```bash
    docker run --rm modem-harness
    ```

---

## Part B — Two boxes: a placeholder "simulator" and "harness"

"docker compose" is a way to define and run several boxes at once from one file.
Today the two boxes are stand-ins; the real simulator and harness replace them
later.

- [ ] **4. Create a placeholder server, `sim_stub.py`** (pretends to be the
      modem — just echoes back whatever it receives over TCP):
    ```python
    """
    sim_stub.py — Day 2 placeholder for the modem simulator.

    Purpose: prove that one container can run a TCP server that another
    container connects to. This is a STAND-IN. On Day 3 the real modem
    simulator replaces it. For now it just echoes back whatever it receives
    so we can confirm the two-container network works.
    """

    import socketserver  # Built-in library for simple TCP/UDP servers.


    class EchoHandler(socketserver.StreamRequestHandler):
        """Handles ONE client connection.

        socketserver creates a new instance of this class for every client
        that connects, and calls handle(). StreamRequestHandler gives us:
          - self.rfile : read from the client
          - self.wfile : write back to the client
        """

        def handle(self):
            # Read one line from the client (up to the newline it sends).
            # .strip() removes the trailing newline and whitespace.
            data = self.rfile.readline().strip()

            # Reply with a "SIM_OK: " prefix so logs clearly show the
            # response came from the simulator. b"..." = raw bytes, because
            # TCP sends bytes, not text strings.
            self.wfile.write(b"SIM_OK: " + data + b"\n")


    if __name__ == "__main__":
        # "0.0.0.0" = listen on all interfaces, so the OTHER container can
        # reach us (localhost would only accept connections from inside this
        # same container). 5000 is the port.
        with socketserver.TCPServer(("0.0.0.0", 5000), EchoHandler) as server:
            # flush=True makes the line appear in Docker logs immediately.
            print("sim_stub listening on 5000", flush=True)
            server.serve_forever()  # Run until stopped.
    ```

- [ ] **5. Create a placeholder client, `harness_stub.py`** (pretends to be the
      tester — connects to the sim and sends one message):
    ```python
    """
    harness_stub.py — Day 2 placeholder for the test harness.

    Purpose: prove this container can find and talk to the simulator
    container over the network. STAND-IN — the real pytest harness replaces
    it starting Day 7. For now it sends one command ("AT") and prints the reply.
    """

    import socket  # Lower-level networking: we act as the CLIENT here.
    import time

    # The simulator may take a moment to boot and start listening. Sleeping
    # 2 seconds is a crude but effective way to avoid connecting too early.
    # (Replaced with real retry logic later.)
    time.sleep(2)

    # create_connection opens a TCP connection to (host, port).
    # "sim" is NOT an IP — it's the SERVICE NAME from docker-compose.yml.
    # Docker's built-in DNS resolves it to the right container. This is
    # exactly how the real harness will find the real simulator.
    with socket.create_connection(("sim", 5000)) as conn:
        # sendall guarantees the whole message goes out. b"AT\n" = the "AT"
        # command plus a newline so the server's readline() knows the line ended.
        conn.sendall(b"AT\n")

        # recv(1024) waits for up to 1024 bytes, then we decode bytes -> string
        # and strip the trailing newline.
        reply = conn.recv(1024).decode().strip()
        print("harness got:", reply, flush=True)
    ```
    - *Note:* `"sim"` is not an IP — it's the service name from the compose file
      below. Docker's built-in networking turns it into the right address.

- [ ] **6. Create `docker-compose.yml`** defining both boxes:
    ```yaml
    # docker-compose.yml — defines and runs BOTH containers together.
    # "docker compose up" builds the images, starts every service, and puts
    # them on a shared private network so they reach each other by name.

    services:
      # The simulator container (the "modem").
      sim:
        build: .                      # Build from the Dockerfile in this folder.
        command: python sim_stub.py   # Override the default (pytest) so this
                                      # container runs the server instead.

      # The harness container (the "tester").
      harness:
        build: .
        command: python harness_stub.py
        depends_on:
          - sim                       # Start "sim" first. NOTE: waits for the
                                      # container to START, not for the server to
                                      # be READY — hence the sleep in the harness.
    ```

- [x] **4–7. Two-box setup — ✅ DONE.** Both containers built and ran; logs showed
      `sim_stub listening on 5000` then `harness got: SIM_OK: AT`, harness exited
      with code 0. The two containers found each other by service name over
      Docker's network. (Port 5000 worked — no AirPlay conflict.)
    ```bash
    docker compose up --build
    ```

- [ ] **8. Stop it:** press `Ctrl+C`, then clean up:
    ```bash
    docker compose down
    ```

---

## Part C — Save your work

- [ ] **9. Commit and push:**
    ```bash
    git add .
    git commit -m "Day 2: Docker + compose skeleton, two containers talking"
    git push
    ```
    - Note: your CI still just runs `pytest`, so it'll stay green. Wiring compose
      into CI happens later (Day 15), not now.

---

## If something breaks

- **`docker build` can't find `requirements.txt`:** you're not running the
  command from the repo root, or the file isn't committed. `ls` should show
  `requirements.txt` next to the `Dockerfile`.
- **Harness can't connect / "connection refused":** the sim box usually just
  needs a second to start. The `time.sleep(2)` handles most cases; if it still
  races, bump it to `3`.
- **`docker compose` says "command not found":** on modern Docker Desktop it's
  `docker compose` (with a space), not the old `docker-compose`. Use the space.
- **Port 5000 already in use:** something else on your Mac uses 5000 (often
  AirPlay Receiver). Either turn that off in System Settings → General → AirDrop
  & Handoff, or change `5000` to `5050` in all three files.

---

## Progress log (updated as we go)

- **Steps 1–2 done.** Dockerfile written, image built clean (`modem-harness`).
  Minor hiccup: first build hit "Dockerfile cannot be empty" (saved before
  pasting) — refilled and rebuilt fine.
- **Housekeeping to do (optional, ~1 min):** the build copied a **23.67 MB**
  context, which means it's dragging `.venv` into the image. Add a
  `.dockerignore` file in the repo root so builds stay small and fast:
    ```
    .venv
    __pycache__/
    *.pyc
    .git
    ```
  Not required for today to work, but do it before the push in step 9.
  **✅ DONE** — `.dockerignore` created with all four entries.
- **Step 3 done.** Container ran isolated (`platform linux`, `/app`) → `1 passed`.
- **Steps 4–7 done.** Two-container skeleton works: `harness got: SIM_OK: AT`.
  No port-5000/AirPlay conflict on this machine.
- **Left today:** stop the containers (step 8), then commit + push (step 9).
- **Day 2 essentially complete** once the push is up.

---

*When you see the harness print `SIM_OK: AT`, Day 2 is done. Day 3 is where the
real work starts: building the actual modem simulator's TCP server.*
