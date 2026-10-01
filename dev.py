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
    subprocess.run(cmd, check=True, cwd=cwd)


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


def _load_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE reader for .env (stdlib only)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _python_env() -> dict[str, str]:
    """Environment for the Python children (api/gateway/worker/beat).

    The root .env is layered on top of the ambient environment so local dev
    picks up APP_KEY, DB_URL, etc. It is deliberately NOT handed to the
    frontend child: the root .env ships empty VITE_* values (the Docker build
    values, meaning same-origin), and Vite gives process env precedence over
    frontend/.env — leaking them would blank out VITE_API_URL and break the
    dashboard under `dev.py run`.
    """
    return {**os.environ, **_load_env_file(ROOT / ".env")}


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
    """Send SIGTERM to the child's whole process group/tree.

    npm/sh spawn vite/node and celery spawns prefork children; terminating
    only the direct child leaves those grandchildren alive holding ports.
    """
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
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        # The group already exited or is not ours; nothing left to signal.
        pass


def _kill_tree_force(proc: subprocess.Popen) -> None:
    """SIGKILL the child's whole process group (POSIX only)."""
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        proc.kill()
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


def run_services(_args: argparse.Namespace) -> None:
    if not PY.exists():
        sys.exit("No venv found. Run `python dev.py setup` first.")

    python_env = _python_env()
    procs = [(name, _spawn(name, cmd, python_env)) for name, cmd in _dev_commands()]

    stopping = False

    def shutdown(*_args: object) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print("\n+ stopping services...", flush=True)
        for _name, proc in procs:
            _kill_tree(proc)
        for _name, proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _kill_tree_force(proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            exited = _first_exit(procs)
            if exited is not None:
                name, code = exited
                print(f"! {name} exited with code {code}; stopping the rest")
                shutdown()
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown()


def admin(rest: list[str]) -> None:
    if not PY.exists():
        sys.exit("No venv found. Run `python dev.py setup` first.")
    if rest and rest[0] == "--":
        rest = rest[1:]
    run([str(PY), "-m", "app.cli", "create-admin", *rest])


def main() -> None:
    parser = argparse.ArgumentParser(prog="dev.py", description="ProxyHub dev bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="create venv, install deps, create .env files")
    sub.add_parser("run", help="run all dev services in one terminal")
    sub.add_parser("admin", help="create an admin user", add_help=False)

    args, extra = parser.parse_known_args()
    if args.command == "admin":
        admin(extra)
    elif extra:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    elif args.command == "setup":
        setup(args)
    elif args.command == "run":
        run_services(args)


if __name__ == "__main__":
    main()
