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

# Conventional ports used when the corresponding .env variable is unset.
DEFAULT_APP_PORT = 8000
DEFAULT_GATEWAY_PORT = 8899
DEFAULT_FRONTEND_PORT = 5173  # Vite dev server default


def _env_int(env: dict[str, str], key: str, default: int) -> int:
    """Read an int from env, falling back to default on missing/invalid values."""
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _ports(env: dict[str, str]) -> tuple[int, int, int]:
    """Resolve (APP_PORT, GATEWAY_PORT, FRONTEND_PORT) from the environment."""
    return (
        _env_int(env, "APP_PORT", DEFAULT_APP_PORT),
        _env_int(env, "GATEWAY_PORT", DEFAULT_GATEWAY_PORT),
        _env_int(env, "FRONTEND_PORT", DEFAULT_FRONTEND_PORT),
    )


def _backend_urls(app_port: int) -> dict[str, str]:
    """Internal API URLs the gateway uses to reach the local backend."""
    base = f"http://127.0.0.1:{app_port}"
    return {
        "GATEWAY_API_URL": f"{base}/internal/proxies",
        "GATEWAY_SESSION_URL": f"{base}/internal/gateway/session",
        "GATEWAY_LOG_URL": f"{base}/internal/logs",
    }


def _frontend_urls(app_port: int) -> dict[str, str]:
    """API/WS URLs the Vite dev server hands to the dashboard."""
    return {
        "VITE_API_URL": f"http://localhost:{app_port}",
        "VITE_WS_URL": f"ws://localhost:{app_port}",
    }


def _cors_origins(existing: str, frontend_port: int) -> str:
    """Ensure the frontend dev origin is present in the CORS allow-list."""
    origins = [o.strip() for o in existing.split(",") if o.strip()]
    for candidate in (
        f"http://localhost:{frontend_port}",
        f"http://127.0.0.1:{frontend_port}",
    ):
        if candidate not in origins:
            origins.append(candidate)
    return ",".join(origins)


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
    picks up APP_KEY, the DB_* variables, etc. It is deliberately NOT handed to the
    frontend child: the root .env ships empty VITE_* values (the Docker build
    values, meaning same-origin), and Vite gives process env precedence over
    frontend/.env — leaking them would blank out VITE_API_URL and break the
    dashboard under `dev.py run`.
    """
    return {**os.environ, **_load_env_file(ROOT / ".env")}


def _dev_commands(
    app_port: int, gateway_port: int, frontend_port: int
) -> list[tuple[str, list[str]]]:
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
                str(app_port),
            ],
        ),
        (
            "frontend",
            _command("npm", "run", "dev", "--", "--port", str(frontend_port)),
        ),
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
                str(gateway_port),
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


def _spawn(name: str, cmd: list[str], env: dict[str, str]) -> subprocess.Popen:
    """Start one dev process with the environment it needs.

    The caller passes the fully-resolved environment for the service; the
    frontend child gets only the ambient environment plus the derived VITE_*
    values (see _python_env for why the root .env is not handed to it), while
    the Python children get the root .env layered in.
    """
    cwd = FRONTEND if name == "frontend" else ROOT
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

    root_env = _python_env()
    app_port, gateway_port, frontend_port = _ports(root_env)

    # Local dev: derive every loopback URL from APP_PORT so changing the port
    # is enough. These override whatever .env shipped for the local case.
    python_env = {
        **root_env,
        **_backend_urls(app_port),
        "CORS_ORIGINS": _cors_origins(root_env.get("CORS_ORIGINS", ""), frontend_port),
    }
    frontend_env = {**os.environ, **_frontend_urls(app_port)}

    env_by_name = {"frontend": frontend_env}
    procs = [
        (name, _spawn(name, cmd, env_by_name.get(name, python_env)))
        for name, cmd in _dev_commands(app_port, gateway_port, frontend_port)
    ]

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
