"""CLI entry points for common project actions (`uv run start`, etc.)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import psutil
from alembic.config import Config

from alembic import command
from tgbot.__main__ import main as bot_main
from tgbot.config import PROJECT_ROOT

PID_FILE = PROJECT_ROOT / ".bot.pid"


def start() -> int:
    """Start one bot process and record it for ``uv run stop``."""
    existing = _read_process()
    if existing is not None:
        print(f"Bot is already running (PID {existing.pid}).")
        return 1
    PID_FILE.unlink(missing_ok=True)

    process = psutil.Process(os.getpid())
    payload = {
        "pid": process.pid,
        "created_at": process.create_time(),
    }
    try:
        with PID_FILE.open("x", encoding="utf-8", newline="\n") as pid_file:
            json.dump(payload, pid_file)
            pid_file.write("\n")
    except FileExistsError:
        print("Another bot process is starting.")
        return 1

    try:
        return bot_main()
    finally:
        _remove_pid_file(process.pid)


def stop() -> int:
    """Stop the bot process recorded by ``uv run start``."""
    process = _read_process()
    if process is None:
        PID_FILE.unlink(missing_ok=True)
        print("Bot is not running.")
        return 0

    pid = process.pid
    try:
        process.terminate()
        try:
            process.wait(timeout=10)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        pass
    except psutil.AccessDenied:
        print(f"Cannot stop bot process {pid}: access denied.")
        return 2
    finally:
        if not psutil.pid_exists(pid):
            _remove_pid_file()

    print(f"Bot stopped (PID {pid}).")
    return 0


def _read_process(path: Path = PID_FILE) -> psutil.Process | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        process = psutil.Process(int(payload["pid"]))
        if abs(process.create_time() - float(payload["created_at"])) > 0.01:
            return None
        return process
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        psutil.NoSuchProcess,
    ):
        return None


def _remove_pid_file(expected_pid: int | None = None) -> None:
    if expected_pid is not None:
        process = _read_process()
        if process is not None and process.pid != expected_pid:
            return
    PID_FILE.unlink(missing_ok=True)


def migrate() -> int:
    """Upgrade the configured database to the latest revision."""
    command.upgrade(alembic_config(), "head")
    return 0


def check() -> int:
    """Check that SQLAlchemy metadata matches the migrated database."""
    command.check(alembic_config())
    return 0


def alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def test() -> int:
    """Run the project test suite."""
    import pytest

    return pytest.main()


def format_code() -> int:
    """Format the project with Ruff."""
    from ruff.__main__ import find_ruff_bin

    return os.spawnv(os.P_WAIT, find_ruff_bin(), ["ruff", "format", "."])


def lint() -> int:
    """Lint the project with Ruff and apply safe autofixes."""
    from ruff.__main__ import find_ruff_bin

    ruff = find_ruff_bin()
    check_code = os.spawnv(
        os.P_WAIT,
        ruff,
        ["ruff", "check", "--fix", "."],
    )
    if check_code != 0:
        return check_code
    return os.spawnv(os.P_WAIT, ruff, ["ruff", "format", "--check", "."])


def typecheck() -> int:
    """Type-check the active packages with Pyright."""
    import subprocess
    import sys

    return subprocess.call(
        [
            sys.executable,
            "-m",
            "pyright",
            "tgbot",
            "scripts/oald",
            "scripts/cli.py",
        ]
    )
