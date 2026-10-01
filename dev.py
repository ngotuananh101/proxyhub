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


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=cwd, shell=IS_WINDOWS)


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
        run(["npm", "install"], cwd=FRONTEND)
    print(
        "\nSetup done. Before production use, edit .env (APP_KEY, INTERNAL_API_KEY, DB_PASSWORD)."
    )


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
        ("frontend", ["npm", "run", "dev"]),
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


def run_services(_args: argparse.Namespace) -> None:
    if not PY.exists():
        sys.exit("No venv found. Run `python dev.py setup` first.")

    procs: list[tuple[str, subprocess.Popen]] = []
    for name, cmd in _dev_commands():
        cwd = FRONTEND if name == "frontend" else ROOT
        print(f"+ starting {name}: {' '.join(cmd)}", flush=True)
        procs.append((name, subprocess.Popen(cmd, cwd=cwd, shell=IS_WINDOWS)))

    stopping = False

    def shutdown(*_args: object) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print("\n+ stopping services...", flush=True)
        for _name, proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for _name, proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            for name, proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"! {name} exited with code {code}; stopping the rest")
                    shutdown()
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown()


def admin(args: argparse.Namespace) -> None:
    if not PY.exists():
        sys.exit("No venv found. Run `python dev.py setup` first.")
    run([str(PY), "-m", "app.cli", "create-admin", *args.rest])


def main() -> None:
    parser = argparse.ArgumentParser(prog="dev.py", description="ProxyHub dev bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="create venv, install deps, create .env files")
    sub.add_parser("run", help="run all dev services in one terminal")
    admin_parser = sub.add_parser("admin", help="create an admin user")
    admin_parser.add_argument("rest", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    {"setup": setup, "run": run_services, "admin": admin}[args.command](args)


if __name__ == "__main__":
    main()
