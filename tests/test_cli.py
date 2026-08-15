# tests/test_cli.py
import subprocess
import sys


def test_cli_create_admin_help():
    result = subprocess.run(
        [sys.executable, "-m", "app.cli", "--help"],
        capture_output=True, text=True, cwd=".",
    )
    assert result.returncode == 0
    assert "create-admin" in result.stdout
