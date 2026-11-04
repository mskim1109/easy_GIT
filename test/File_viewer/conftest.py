import os
import subprocess
import time
from pathlib import Path

import pytest


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """사용자 git 설정과 떨어진 임시 git 저장소."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "test")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "core.autocrlf", "false")
    return root


def write(root: Path, rel: str, data: str | bytes) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return p


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          encoding="utf-8", check=True).stdout


async def settle(app, pilot):
    for _ in range(2):
        await app.workers.wait_for_complete()
        await pilot.pause()


async def wait_until(pred, app, pilot, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not pred():
        if time.monotonic() > deadline:
            raise AssertionError("wait_until: 시간 안에 조건이 참이 되지 않음")
        await settle(app, pilot)
