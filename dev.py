#!/usr/bin/env python3
"""Cross-platform dev bootstrap for ProxyHub.

Commands:
    python dev.py setup    # create venv, install deps, create .env files, npm install
    python dev.py run      # run api + frontend + gateway + celery worker + beat
    python dev.py admin    # passthrough to `python -m app.cli create-admin`
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IS_WINDOWS = os.name == "nt"
VENV_DIR = ROOT / "venv"
VENV_BIN = VENV_DIR / ("Scripts" if IS_WINDOWS else "bin")
PY = VENV_BIN / ("python.exe" if IS_WINDOWS else "python")
FRONTEND = ROOT / "frontend"
SHUTDOWN_GRACE_SECONDS = 10


def _venv_script(name: str) -> str:
    suffix = ".exe" if IS_WINDOWS else ""
    return str(VENV_BIN / f"{name}{suffix}")


def _command(name: str, *args: str) -> list[str]:
    """Build an argv for a bare executable name, safe for ``shell=False``.

    On Windows ``npm`` resolves to ``npm.cmd``, which ``CreateProcess`` cannot
    launch directly, so it is routed through ``cmd.exe``. Every other command
    here uses an absolute path, so no shell is needed on either platform.
    """
    exe = shutil.which(name) or name
    if IS_WINDOWS and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe, *args]
    return [exe, *args]


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    # `cmd` is a fixed argv of literal flags plus argparse-validated values
    # (see admin()); it is never run through a shell and no untrusted string
    # is re-parsed as an option. Sonar's S8705 (CWE-88) flags the argv
    # passthrough generically, but this local dev bootstrap has no
    # attacker-controlled request feeding it — suppressed as a false positive.
    subprocess.run(cmd, check=True, cwd=cwd)  # NOSONAR


def ensure_env_file(src: Path, dst: Path) -> None:
    if dst.exists():
        print(f"= {dst.relative_to(ROOT)} already exists, leaving it untouched")
        return
    if not src.exists():
        print(f"! {src.relative_to(ROOT)} not found; skipping")
        return
    shutil.copyfile(src, dst)
    print(f"+ created {dst.relative_to(ROOT)} from {src.name}")


def setup(_args: argparse.Namespace) -> None:
    if not PY.exists():
        print("+ creating virtualenv in ./venv")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    run([str(PY), "-m", "pip", "install", "-r", "requirements-dev.txt"])
    ensure_env_file(ROOT / ".env.example", ROOT / ".env")
    ensure_env_file(FRONTEND / ".env.example", FRONTEND / ".env")
    if (FRONTEND / "node_modules").exists():
        print("= frontend/node_modules already present")
    else:
        run(_command("npm", "install"), cwd=FRONTEND)
    print(
        "\nSetup done. Before production use, edit .env (APP_KEY, INTERNAL_API_KEY, DB_PASSWORD)."
    )


def _parse_env_value(raw: str) -> str:
    """Parse the right-hand side of a .env assignment.

    Handles what humans actually write: `export ` prefixes, single or double
    quotes (which keep `#` literal, even when a comment follows), and a
    trailing ` # comment` on unquoted values.
    """
    value = raw.strip()
    if value and value[0] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[1:end]
        return value[1:]
    # A `#` only starts a comment when it follows whitespace, as in dotenv.
    for i, char in enumerate(value):
        if char == "#" and (i == 0 or value[i - 1].isspace()):
            value = value[:i]
            break
    return value.strip()


def _load_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE reader for .env (stdlib only)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
            if "=" not in line:
                continue
        key, _, raw = line.partition("=")
        values[key.strip()] = _parse_env_value(raw)
    return values


def _load_and_merge(path: Path) -> dict[str, str]:
    """File values under the process environment: the shell always wins.

    Exported variables are explicit operator intent (and how CI configures a
    run); a stale .env copied by `setup` must not silently override them.
    """
    return {**_load_env_file(path), **os.environ}


def _python_env() -> dict[str, str]:
    """Environment for the Python children (api/gateway/worker/beat).

    The root .env is layered under the ambient environment so local dev picks
    up APP_KEY, DB_URL, etc. It is deliberately NOT handed to the frontend
    child: the root .env ships empty VITE_* values (the Docker build values,
    meaning same-origin), and Vite gives process env precedence over
    frontend/.env — leaking them would blank out VITE_API_URL and break the
    dashboard under `dev.py run`.
    """
    return _load_and_merge(ROOT / ".env")


def _dev_commands() -> list[tuple[str, list[str]]]:
    # Celery needs the threads pool on Windows; the default prefork pool is
    # unsupported there.
    worker_pool = ["--pool=threads", "--concurrency=8"] if IS_WINDOWS else []
    return [
        (
            "api",
            [
                _venv_script("uvicorn"),
                "app.main:app",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
        ),
        ("frontend", _command("npm", "run", "dev")),
        (
            "gateway",
            [
                str(PY),
                "-m",
                "proxy",
                "--plugins",
                "app.gateway.plugin.RotateProxyPlugin",
                "--hostname",
                "127.0.0.1",
                "--port",
                "8899",
            ],
        ),
        (
            "worker",
            [
                _venv_script("celery"),
                "-A",
                "app.worker.celery_app",
                "worker",
                "--loglevel=info",
                *worker_pool,
            ],
        ),
        (
            "beat",
            [
                _venv_script("celery"),
                "-A",
                "app.worker.celery_app",
                "beat",
                "--loglevel=info",
            ],
        ),
    ]


def _kill_tree(proc: subprocess.Popen) -> None:
    """Ask the child's whole process group/tree to stop.

    npm/sh spawn vite/node and celery spawns prefork children; terminating
    only the direct child leaves those grandchildren alive holding ports.
    """
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        # No /F: give the children a chance to shut down cleanly. A process
        # that ignores WM_CLOSE is caught by the grace period, after which
        # _kill_tree_force runs taskkill /F. `taskkill /F` here would kill
        # workers mid-write.
        subprocess.run(
            ["taskkill", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        # The group already exited or is not ours; nothing left to signal.
        pass


def _kill_tree_force(proc: subprocess.Popen) -> None:
    """SIGKILL the child's whole process group."""
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _spawn(name: str, cmd: list[str], python_env: dict[str, str]) -> subprocess.Popen:
    """Start one dev process with the environment it needs.

    The frontend child gets only the ambient environment so `npm run dev`
    reads frontend/.env (see _python_env); the Python children get the root
    .env layered in.
    """
    if name == "frontend":
        cwd, env = FRONTEND, dict(os.environ)
    else:
        cwd, env = ROOT, python_env
    print(f"+ starting {name}: {' '.join(cmd)}", flush=True)
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        start_new_session=not IS_WINDOWS,
    )


def _first_exit(procs: list[tuple[str, subprocess.Popen]]) -> tuple[str, int] | None:
    """Return (name, exit code) of the first process that has exited, if any."""
    for name, proc in procs:
        code = proc.poll()
        if code is not None:
            return name, code
    return None


def _make_shutdown(procs: list[tuple[str, subprocess.Popen]]):
    """Build the shutdown handler.

    `exit_code` is what `dev.py run` exits with: a child dying on its own is a
    failure (non-zero, so CI and `&&` chains notice), while Ctrl-C/SIGTERM is a
    normal stop (zero).
    """
    stopping = False

    def shutdown(exit_code: int | None = 0) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print("\n+ stopping services...", flush=True)
        for _name, proc in procs:
            _kill_tree(proc)
        for _name, proc in procs:
            try:
                proc.wait(timeout=SHUTDOWN_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                _kill_tree_force(proc)
        sys.exit(exit_code or 0)

    return shutdown


def run_services(_args: argparse.Namespace) -> None:
    if not PY.exists():
        sys.exit("No venv found. Run `python dev.py setup` first.")

    python_env = _python_env()
    procs = [(name, _spawn(name, cmd, python_env)) for name, cmd in _dev_commands()]
    shutdown = _make_shutdown(procs)

    # The signal handlers receive (signum, frame); the exit code is ours to pick.
    signal.signal(signal.SIGINT, lambda *_: shutdown(0))
    signal.signal(signal.SIGTERM, lambda *_: shutdown(0))

    try:
        while True:
            exited = _first_exit(procs)
            if exited is not None:
                name, code = exited
                print(f"! {name} exited with code {code}; stopping the rest")
                shutdown(code)
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown(0)


def admin(args: argparse.Namespace) -> None:
    if not PY.exists():
        sys.exit("No venv found. Run `python dev.py setup` first.")
    # Arguments are declared explicitly (not forwarded verbatim), so a caller
    # cannot smuggle extra flags into the CLI. Values are passed as a single
    # `--opt=value` token each, which cannot be re-parsed as a separate flag.
    cmd = [
        str(PY),
        "-m",
        "app.cli",
        "create-admin",
        f"--username={args.username}",
        f"--password={args.password}",
    ]
    if args.email:
        cmd.append(f"--email={args.email}")
    run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(prog="dev.py", description="ProxyHub dev bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="create venv, install deps, create .env files")
    sub.add_parser("run", help="run all dev services in one terminal")
    admin_parser = sub.add_parser("admin", help="create an admin user")
    admin_parser.add_argument("--username", required=True)
    admin_parser.add_argument("--email")
    admin_parser.add_argument("--password", required=True)

    args = parser.parse_args()
    if args.command == "admin":
        admin(args)
    elif args.command == "setup":
        setup(args)
    elif args.command == "run":
        run_services(args)


if __name__ == "__main__":
    main()
