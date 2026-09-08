"""Thin git helpers so saved icons and diagrams land in the repo."""

from __future__ import annotations

import subprocess
from typing import List, Tuple

from .store import ROOT

TRACKED = ["icons", "diagrams", "exports"]


def git(*args: str) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(ROOT), capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def is_repo() -> bool:
    code, out = git("rev-parse", "--is-inside-work-tree")
    return code == 0 and out.strip() == "true"


def init() -> Tuple[int, str]:
    return git("init", "-b", "main")


def branch() -> str:
    # --show-current works before the first commit exists; rev-parse errors there.
    code, out = git("branch", "--show-current")
    return out.strip() if code == 0 else ""


def remotes() -> List[str]:
    code, out = git("remote")
    return [r for r in out.splitlines() if r] if code == 0 else []


def remote_url(name: str = "origin") -> str:
    code, out = git("remote", "get-url", name)
    return out.strip() if code == 0 else ""


def status() -> str:
    code, out = git("status", "--short")
    return out if code == 0 else f"git error: {out}"


def pending_changes() -> List[str]:
    code, out = git("status", "--porcelain", "--", *TRACKED)
    return [line for line in out.splitlines() if line.strip()] if code == 0 else []


def commit(message: str, paths: List[str] = None) -> Tuple[bool, str]:
    targets = paths if paths is not None else TRACKED
    code, out = git("add", "--", *targets)
    if code != 0:
        return False, out
    code, out = git("commit", "-m", message)
    if code != 0:
        if "nothing to commit" in out:
            return False, "Nothing to commit - the library matches the last commit."
        return False, out
    return True, out


def push(remote: str = "origin") -> Tuple[bool, str]:
    current = branch() or "main"
    code, out = git("push", "-u", remote, current)
    return code == 0, out
