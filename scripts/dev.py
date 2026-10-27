#!/usr/bin/env python3
"""
One launcher for the whole system: bridge API, frontend, smoke test, pytest, and
a live view of the API calls passing through the bridge.

    python scripts/dev.py up                  backend :$BACKEND_PORT (8000) + vite frontend :5173
    python scripts/dev.py up --docker         backend + the nginx image on :3000
    python scripts/dev.py up --no-frontend    backend only
    python scripts/dev.py up --offline        same, but USE_FAKE_LLM=1 by default
    python scripts/dev.py up --reload         uvicorn restarts on code edits
    python scripts/dev.py monitor             follow the API calls of a running `up`
    python scripts/dev.py smoke               smoke_backend.py (starts a server if needed)
    python scripts/dev.py test                pytest tests/
    python scripts/dev.py check               preflight + config only, starts nothing

Everything this starts, it stops again on Ctrl-C — including the docker
container and any uvicorn reload children. Output from both services is merged,
prefixed, and mirrored to logs/dev/<name>-<timestamp>.log, so `monitor` can
follow the API access lines from a second terminal while `up` keeps running.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs" / "dev"
FRONTEND_DIR = ROOT / "frontend"
COMPOSE_FILE = FRONTEND_DIR / "docker-compose.yml"

VITE_PORT = 5173
DOCKER_PORT = 3000

# uvicorn's venv python — the project convention is to call it explicitly rather
# than rely on an activated shell.
VENV_PY = ROOT / ".venv" / "bin" / "python"

DIM, RED, GREEN, YELLOW, BLUE, MAGENTA, RESET = (
    "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[0m",
)

# "127.0.0.1:52345 - "GET /api/health HTTP/1.1" 200" — uvicorn's access line.
ACCESS_RE = re.compile(r'"(?P<method>[A-Z]+) (?P<path>\S+) HTTP/[\d.]+" (?P<status>\d{3})')


def env_value(key: str) -> str:
    """Read one key out of the environment or .env without importing config
    (keeps this script runnable even when the venv is half-built)."""
    if (live := os.getenv(key, "").strip()):
        return live
    env_file = ROOT / ".env"
    if not env_file.exists():
        return ""
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# One port for the bridge API, defined in config.py as BACKEND_PORT and read
# here from the same env var rather than through an import (above). Everything
# that talks to the backend — the Vite proxy, nginx, smoke_backend.py — has to
# resolve to this same number, or you test a server nobody is serving (#40, #85).
BACKEND_PORT = int(env_value("BACKEND_PORT") or 8000)
HEALTH_URL = f"http://127.0.0.1:{BACKEND_PORT}/api/health"


def py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.connect_ex(("127.0.0.1", port)) != 0


def backend_healthy(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError):
        return False


# What a server loads. A .py newer than the server's start time means it runs older code than
# the tree it is graded against (bug #85 item 4: a pre-cv_link server passed smoke on 10-14).
_SOURCE_DIRS = ("backend", "agents", "state", "utils", "vectordb", "learning", "evaluation", "prompts")


def stale_server_reason() -> str | None:
    """None if the server on BACKEND_PORT started after the newest source file changed.
    Otherwise a one-line reason. A /api/health with no `started` is itself a stale server."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2.0) as r:
            started = json.loads(r.read().decode()).get("started")
    except (urllib.error.URLError, OSError, ValueError):
        return "could not read /api/health"
    if not started:
        return "its /api/health has no `started` field, so it predates this check"
    started_at = datetime.fromisoformat(started).timestamp()
    files = [ROOT / "config.py"]
    for d in _SOURCE_DIRS:
        files += [p for pat in ("*.py", "*.yaml") for p in (ROOT / d).rglob(pat)]
    newest = max(files, key=lambda p: p.stat().st_mtime)
    if newest.stat().st_mtime > started_at:
        return f"{newest.relative_to(ROOT)} changed after the server started ({started})"
    return None


def wait_healthy(timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if backend_healthy():
            return True
        time.sleep(0.4)
    return False


# -----------------------------------------------------------------------------
# Service supervision
# -----------------------------------------------------------------------------
class Service:
    """One child process whose output is prefixed, colored, and tee'd to a file."""

    def __init__(self, name: str, cmd: list[str], color: str, cwd: Path,
                 env: dict | None = None, stop_cmd: list[str] | None = None):
        self.name = name
        self.cmd = cmd
        self.color = color
        self.cwd = cwd
        self.env = env or {}
        self.stop_cmd = stop_cmd
        self.proc: subprocess.Popen | None = None
        self.log_path: Path | None = None
        self.calls: Counter = Counter()
        self._thread: threading.Thread | None = None

    def start(self, stamp: str) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = LOG_DIR / f"{self.name}-{stamp}.log"

        env = {**os.environ, "PYTHONUNBUFFERED": "1", **self.env}
        self.proc = subprocess.Popen(
            self.cmd,
            cwd=str(self.cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # uvicorn splits access/error across both
            text=True,
            bufsize=1,
            start_new_session=True,  # own process group, so Ctrl-C is ours to forward
        )
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout and self.log_path
        tag = f"{self.color}[{self.name}]{RESET}"
        with self.log_path.open("w") as log:
            for line in self.proc.stdout:
                line = line.rstrip("\n")
                log.write(line + "\n")
                log.flush()

                hit = ACCESS_RE.search(line)
                if hit:
                    self.calls[f"{hit['method']} {hit['path'].split('?')[0]}"] += 1
                    status = int(hit["status"])
                    color = GREEN if status < 400 else (YELLOW if status < 500 else RED)
                    print(f"{tag} {color}{hit['status']}{RESET} "
                          f"{hit['method']:<6} {hit['path']}")
                else:
                    print(f"{tag} {line}")

    def stop(self) -> None:
        if self.stop_cmd:
            subprocess.run(self.stop_cmd, cwd=str(self.cwd),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not self.proc or self.proc.poll() is not None:
            return
        try:
            # Kill the group, not just the leader: uvicorn --reload and npm both
            # spawn children that would otherwise survive and hold the port.
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def supervise(services: list[Service]) -> int:
    """Start everything, block until Ctrl-C or a child dies, then tear down."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stopping = threading.Event()

    def shutdown(_sig=None, _frame=None):
        if stopping.is_set():
            return
        stopping.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for svc in services:
        print(f"{DIM}starting {svc.name}: {' '.join(svc.cmd)}{RESET}")
        svc.start(stamp)

    exit_code = 0
    try:
        while not stopping.is_set():
            for svc in services:
                if svc.proc and svc.proc.poll() is not None:
                    print(f"\n{RED}{svc.name} exited with code "
                          f"{svc.proc.returncode}{RESET}")
                    exit_code = svc.proc.returncode or 1
                    stopping.set()
            time.sleep(0.3)
    finally:
        print(f"\n{DIM}stopping…{RESET}")
        for svc in reversed(services):
            svc.stop()
        report_calls(services)
        for svc in services:
            if svc.log_path:
                print(f"{DIM}  log: {svc.log_path.relative_to(ROOT)}{RESET}")
    return exit_code


def report_calls(services: list[Service]) -> None:
    total = Counter()
    for svc in services:
        total.update(svc.calls)
    if not total:
        return
    print(f"\n{DIM}API calls this session{RESET}")
    for route, count in total.most_common():
        print(f"  {count:>4}  {route}")


# -----------------------------------------------------------------------------
# Service definitions
# -----------------------------------------------------------------------------
def backend_service(offline: bool = False, reload: bool = False) -> Service:
    cmd = [py(), "-m", "uvicorn", "scripts.frontend_api:app",
           "--port", str(BACKEND_PORT), "--host", "127.0.0.1"]
    if reload:
        cmd.append("--reload")
    env = {"USE_FAKE_LLM": "1"} if offline else {}
    return Service("backend", cmd, BLUE, ROOT, env)


def vite_service() -> Service:
    # vite.config.js reads BACKEND_PORT for its /api proxy target, so hand it the
    # same number this launcher is serving on rather than letting it default.
    return Service("frontend", ["npm", "run", "dev", "--", "--port", str(VITE_PORT)],
                   MAGENTA, FRONTEND_DIR, {"BACKEND_PORT": str(BACKEND_PORT)})


def docker_service() -> Service:
    return Service(
        "frontend",
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "--build"],
        MAGENTA,
        FRONTEND_DIR,
        stop_cmd=["docker", "compose", "-f", str(COMPOSE_FILE), "down"],
    )


# -----------------------------------------------------------------------------
# Preflight
# -----------------------------------------------------------------------------
def preflight(need_frontend: bool, docker: bool, need_backend: bool = True) -> list[str]:
    problems: list[str] = []

    if not VENV_PY.exists():
        problems.append(f"no venv at {VENV_PY} — falling back to {sys.executable}")

    if not env_value("ADMIN_TOKEN"):
        problems.append(
            "ADMIN_TOKEN is empty in .env — no access request can be approved, so "
            "no user token can be issued and the UI stays on the login screen.\n"
            "      generate one:  python -c \"import secrets; "
            "print(secrets.token_urlsafe(32))\""
        )

    if need_backend and not port_free(BACKEND_PORT):
        problems.append(
            f"port {BACKEND_PORT} is already in use — another backend is running.\n"
            f"      watch it instead:  python scripts/dev.py monitor\n"
            f"      or find it:        lsof -ti:{BACKEND_PORT}"
        )

    if need_frontend and not docker:
        if not (FRONTEND_DIR / "node_modules").exists():
            problems.append(
                "frontend/node_modules is missing — run:  cd frontend && npm install\n"
                "      (or use --docker, which builds node inside the image)"
            )
        if not port_free(VITE_PORT):
            problems.append(f"port {VITE_PORT} is already in use")

    if need_frontend and docker and not port_free(DOCKER_PORT):
        problems.append(f"port {DOCKER_PORT} is already in use")

    return problems


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------
def cmd_up(args: argparse.Namespace) -> int:
    want_frontend = not args.no_frontend
    problems = preflight(want_frontend, args.docker)
    fatal = [p for p in problems if "no venv at" not in p and "ADMIN_TOKEN" not in p]
    for p in problems:
        print(f"{YELLOW}!{RESET} {p}")
    if fatal:
        return 1

    services = [backend_service(offline=args.offline, reload=args.reload)]
    if want_frontend:
        services.append(docker_service() if args.docker else vite_service())

    ui_port = DOCKER_PORT if args.docker else VITE_PORT
    print(f"\n{GREEN}bridge API{RESET}  http://127.0.0.1:{BACKEND_PORT}/api/health")
    if want_frontend:
        print(f"{GREEN}dashboard {RESET}  http://localhost:{ui_port}")
    if args.offline:
        print(f"{DIM}USE_FAKE_LLM=1 — runs default to the fake LLM, no provider spend{RESET}")
    print(f"{DIM}Ctrl-C stops everything. API calls appear below as they happen.{RESET}\n")

    return supervise(services)


def cmd_monitor(args: argparse.Namespace) -> int:
    """Follow a running backend's log from a second terminal."""
    if args.file:
        # Resolved: relative_to(ROOT) below raises on a relative path ("logs/dev/x.log").
        log_path = Path(args.file).resolve()
    else:
        logs = sorted(LOG_DIR.glob("backend-*.log"))
        if not logs:
            print(f"{RED}no backend log in {LOG_DIR.relative_to(ROOT)} — "
                  f"start one with: python scripts/dev.py up{RESET}")
            return 1
        log_path = logs[-1]

    shown = log_path.relative_to(ROOT) if log_path.is_relative_to(ROOT) else log_path
    print(f"{DIM}following {shown}"
          f"{'' if args.all else ' (API calls only — use --all for everything)'}"
          f"{RESET}\n")

    calls: Counter = Counter()
    try:
        with log_path.open() as f:
            if not args.from_start:
                f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.25)
                    continue
                line = line.rstrip("\n")
                hit = ACCESS_RE.search(line)
                if hit:
                    calls[f"{hit['method']} {hit['path'].split('?')[0]}"] += 1
                    status = int(hit["status"])
                    color = GREEN if status < 400 else (YELLOW if status < 500 else RED)
                    stamp = datetime.now().strftime("%H:%M:%S")
                    print(f"{DIM}{stamp}{RESET} {color}{hit['status']}{RESET} "
                          f"{hit['method']:<6} {hit['path']}")
                elif args.all:
                    print(f"{DIM}{line}{RESET}")
    except KeyboardInterrupt:
        if calls:
            print(f"\n{DIM}seen this session{RESET}")
            for route, count in calls.most_common():
                print(f"  {count:>4}  {route}")
        return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    """Run the end-to-end smoke test, starting a server only if none is up."""
    started: Service | None = None
    scratch: Path | None = None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if backend_healthy():
        print(f"{DIM}using the backend already on :{BACKEND_PORT}{RESET}")
        # #85 item 4: a stale server graded as if current is worse than no smoke run.
        if (why := stale_server_reason()) and not args.allow_stale:
            print(f"{RED}stale server on :{BACKEND_PORT}: {why}. Restart it, or pass "
                  f"--allow-stale to grade it anyway{RESET}")
            return 1
        # #86 item 3: the smoke user's account, CV and runs land wherever THAT server keeps them.
        print(f"{YELLOW}that server's own account/upload/run folders get the smoke test's data — "
              f"stop it and rerun to use a throwaway set{RESET}")
    else:
        if not port_free(BACKEND_PORT):
            print(f"{RED}port {BACKEND_PORT} is busy but /api/health does not "
                  f"answer — stop whatever holds it first{RESET}")
            return 1
        print(f"{DIM}starting a backend for the smoke run…{RESET}")
        started = backend_service(offline=args.offline)
        # #86 item 3: a server this command starts keeps its accounts, uploads and run logs in a
        # temp folder, removed at the end, so smoke users never reach knowledge_base/auth/.
        scratch = Path(tempfile.mkdtemp(prefix="smoke-"))
        started.env.update({"KB_AUTH_DIR": str(scratch / "auth"),
                            "CV_UPLOADS_DIR": str(scratch / "uploads"),
                            "RUNS_DIR": str(scratch / "runs")})
        print(f"{DIM}smoke data goes to {scratch}, deleted afterwards{RESET}")
        started.start(stamp)
        if not wait_healthy():
            print(f"{RED}backend never became healthy — see "
                  f"{started.log_path}{RESET}")
            started.stop()
            return 1

    try:
        base = f"http://127.0.0.1:{BACKEND_PORT}/api"
        # #85: the smoke test used to be hard-wired to :8000 while this launcher
        # served :8002, so it graded a stale server from a previous week and one
        # of its checks spent a real allowance run. The target is now built from
        # BACKEND_PORT — assert that before spending anything, and print it so a
        # wrong port is visible in the transcript rather than inferred afterwards.
        if urllib.parse.urlparse(base).port != BACKEND_PORT:
            print(f"{RED}smoke target {base} is not the backend port "
                  f"({BACKEND_PORT}) — refusing to grade another server{RESET}")
            return 1
        print(f"{DIM}smoke test target: {base}  (BACKEND_PORT={BACKEND_PORT}){RESET}")
        return subprocess.run([py(), str(ROOT / "scripts" / "smoke_backend.py")],
                              cwd=str(ROOT), env={**os.environ, "SMOKE_BASE": base}).returncode
    finally:
        if started:
            print(f"\n{DIM}stopping the backend this run started…{RESET}")
            started.stop()
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)


def cmd_test(args: argparse.Namespace) -> int:
    cmd = [py(), "-m", "pytest", "tests/", "-q"]
    if args.pytest_args:
        cmd = [py(), "-m", "pytest", *args.pytest_args]
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def cmd_check(args: argparse.Namespace) -> int:
    print(f"{DIM}preflight{RESET}")
    problems = preflight(need_frontend=True, docker=False, need_backend=False)
    if problems:
        for p in problems:
            print(f"{YELLOW}!{RESET} {p}")
    else:
        print(f"{GREEN}✓{RESET} venv, .env and frontend deps look fine")

    print(f"\n{DIM}backend{RESET}")
    print(f"{GREEN}✓{RESET} running on :{BACKEND_PORT}" if backend_healthy()
          else f"{DIM}·{RESET} not running")

    print(f"\n{DIM}config{RESET}")
    return subprocess.run([py(), str(ROOT / "main.py")], cwd=str(ROOT)).returncode


# -----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="dev.py",
        description="Run, test and watch the whole system from one place.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="run the backend and frontend together")
    up.add_argument("--docker", action="store_true",
                    help=f"serve the built frontend via docker on :{DOCKER_PORT}")
    up.add_argument("--no-frontend", action="store_true", help="backend only")
    up.add_argument("--offline", action="store_true",
                    help="default runs to the fake LLM (USE_FAKE_LLM=1)")
    up.add_argument("--reload", action="store_true",
                    help="uvicorn reloads on code changes")
    up.set_defaults(func=cmd_up)

    mon = sub.add_parser("monitor", help="follow the API calls of a running backend")
    mon.add_argument("--all", action="store_true",
                     help="show every log line, not just API calls")
    mon.add_argument("--from-start", action="store_true",
                     help="replay the log from the beginning")
    mon.add_argument("--file", help="follow a specific log file")
    mon.set_defaults(func=cmd_monitor)

    smoke = sub.add_parser("smoke", help="end-to-end smoke test against a real server")
    smoke.add_argument("--allow-stale", action="store_true",
                       help="grade a server that started before the code last changed")
    smoke.add_argument("--offline", action="store_true",
                       help="start the server with USE_FAKE_LLM=1 if one is needed")
    smoke.set_defaults(func=cmd_smoke)

    test = sub.add_parser("test", help="pytest tests/")
    test.add_argument("pytest_args", nargs="*",
                      help="passed straight through to pytest")
    test.set_defaults(func=cmd_test)

    check = sub.add_parser("check", help="preflight + config, starts nothing")
    check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
