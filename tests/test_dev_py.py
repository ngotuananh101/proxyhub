"""dev.py's .env handling and shutdown behaviour.

The bootstrap layers root .env under the real environment, so a value exported
in the shell (or set by CI) must win over the file. The file itself is written
by humans, so quoted values, `export ` prefixes and trailing comments all have
to parse.
"""
import os

import pytest

import dev


def test_process_env_wins_over_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DB_URL=from_file\n")
    monkeypatch.setenv("DB_URL", "from_shell")
    assert dev._load_and_merge(tmp_path / ".env")["DB_URL"] == "from_shell"


def test_dotenv_parses_quotes_export_and_comments(tmp_path):
    p = tmp_path / ".env"
    p.write_text('export APP_KEY="a#b"\n# comment\nNAME=plain # trailing\n')
    values = dev._load_env_file(p)
    assert values["APP_KEY"] == "a#b"
    assert values["NAME"] == "plain"


def test_dotenv_keeps_hash_inside_single_quotes(tmp_path):
    p = tmp_path / ".env"
    p.write_text("HASH='x # y' # real comment\nEMPTY=\n")
    values = dev._load_env_file(p)
    assert values["HASH"] == "x # y"
    assert values["EMPTY"] == ""


def test_dotenv_ignores_malformed_lines(tmp_path):
    p = tmp_path / ".env"
    p.write_text("no_equals_sign\nKEY=value\n")
    assert dev._load_env_file(p) == {"KEY": "value"}


def test_missing_dotenv_contributes_nothing(tmp_path):
    values = dev._load_and_merge(tmp_path / "absent.env")
    assert values == dict(os.environ)


def test_shutdown_propagates_the_child_exit_code(monkeypatch):
    exited: list[int] = []
    monkeypatch.setattr(dev.sys, "exit", lambda code: exited.append(code))
    monkeypatch.setattr(dev, "_kill_tree", lambda proc: None)
    monkeypatch.setattr(dev, "_kill_tree_force", lambda proc: None)

    proc = _FakeProcess(exit_code=None)
    stop = dev._make_shutdown([("api", proc)])

    # A child dying on its own is a failure: `dev.py run` must exit non-zero so
    # CI and `&&`-chained commands notice.
    stop(3)
    assert exited == [3]
    assert proc.terminated is True


def test_shutdown_exits_zero_on_a_signal(monkeypatch):
    exited: list[int] = []
    monkeypatch.setattr(dev.sys, "exit", lambda code: exited.append(code))
    monkeypatch.setattr(dev, "_kill_tree", lambda proc: None)
    monkeypatch.setattr(dev, "_kill_tree_force", lambda proc: None)

    proc = _FakeProcess(exit_code=None)
    stop = dev._make_shutdown([("api", proc)])
    stop(None)  # Ctrl-C
    assert exited == [0]


def test_shutdown_only_runs_once(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(dev.sys, "exit", lambda code: calls.append(code))
    monkeypatch.setattr(dev, "_kill_tree", lambda proc: None)
    monkeypatch.setattr(dev, "_kill_tree_force", lambda proc: None)

    proc = _FakeProcess(exit_code=None)
    stop = dev._make_shutdown([("api", proc)])
    stop(None)
    stop(None)
    assert calls == [0]


class _FakeProcess:
    def __init__(self, exit_code):
        self._exit_code = exit_code
        self.terminated = False

    def poll(self):
        return self._exit_code

    def wait(self, timeout=None):
        self.terminated = True
        return 0

    def kill(self):
        self.terminated = True


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(dev, "SHUTDOWN_GRACE_SECONDS", 0)
