"""Commit library files straight to GitHub over the API.

Streamlit Community Cloud gives every app an ephemeral disk: anything written to
`icons/` is gone on the next reboot. When a token is configured, every save is
mirrored into the repo as a real commit, so the library survives restarts.

Config comes from environment variables or Streamlit secrets:

    GITHUB_TOKEN   fine-grained PAT with Contents: read/write on the repo
    GITHUB_REPO    "owner/name"
    GITHUB_BRANCH  optional, defaults to "main"
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, Iterable, List, Optional

import requests

API = "https://api.github.com"
TIMEOUT = 30


class GitHubError(RuntimeError):
    pass


def _cfg(name: str, default: str = "") -> str:
    """Environment first, then Streamlit secrets (absent outside the app)."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    try:
        import streamlit as st

        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return default


def token() -> str:
    return _cfg("GITHUB_TOKEN")


def repo() -> str:
    return _cfg("GITHUB_REPO")


def branch() -> str:
    return _cfg("GITHUB_BRANCH", "main") or "main"


def enabled() -> bool:
    return bool(token() and repo())


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "icon-studio",
    }


def _request(method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
    try:
        resp = requests.request(
            method, f"{API}{path}", headers=_headers(), timeout=TIMEOUT, **kwargs
        )
    except requests.RequestException as exc:
        raise GitHubError(f"network error: {exc}") from exc

    if resp.status_code >= 300:
        try:
            detail = resp.json().get("message", "")
        except ValueError:
            detail = resp.text[:200]
        hint = ""
        if resp.status_code in (401, 403):
            hint = " — check the token is valid and has Contents: read/write on this repo"
        elif resp.status_code == 404:
            hint = " — repo not found, or the token can't see it (check GITHUB_REPO)"
        raise GitHubError(f"{resp.status_code} {detail}{hint}")

    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {}


def check() -> Dict[str, Any]:
    """Verify the token can write. Returns repo info; raises GitHubError otherwise."""
    if not enabled():
        raise GitHubError("GITHUB_TOKEN / GITHUB_REPO are not configured")
    info = _request("GET", f"/repos/{repo()}")
    perms = info.get("permissions") or {}
    if not perms.get("push", False):
        raise GitHubError(
            "token can read this repo but not write to it — the PAT needs "
            "Contents: read/write"
        )
    return {
        "repo": info.get("full_name", repo()),
        "branch": branch(),
        "private": info.get("private"),
        "default_branch": info.get("default_branch"),
    }


def remote_paths() -> List[str]:
    """Every file tracked on the branch (used to avoid deleting what isn't there)."""
    ref = _request("GET", f"/repos/{repo()}/git/ref/heads/{branch()}")
    tree = _request(
        "GET",
        f"/repos/{repo()}/git/trees/{ref['object']['sha']}",
        params={"recursive": "1"},
    )
    return [e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"]


def commit_files(
    files: Dict[str, bytes],
    message: str,
    deletes: Optional[Iterable[str]] = None,
) -> str:
    """Write/delete several paths in one commit. Returns the short SHA.

    Uses the git data API rather than the contents API so that an icon and the
    updated manifest land together instead of as two separate commits.
    """
    if not enabled():
        raise GitHubError("GITHUB_TOKEN / GITHUB_REPO are not configured")

    deletes = [p for p in (deletes or []) if p]
    if not files and not deletes:
        return ""

    slug, ref_name = repo(), branch()
    ref = _request("GET", f"/repos/{slug}/git/ref/heads/{ref_name}")
    head = ref["object"]["sha"]
    base_tree = _request("GET", f"/repos/{slug}/git/commits/{head}")["tree"]["sha"]

    tree: List[Dict[str, Any]] = []
    for path, data in files.items():
        blob = _request(
            "POST",
            f"/repos/{slug}/git/blobs",
            json={"content": base64.b64encode(data).decode(), "encoding": "base64"},
        )
        tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    if deletes:
        # Deleting a path that isn't in the tree is a 422, so filter first.
        present = set(remote_paths())
        for path in deletes:
            if path in present:
                tree.append(
                    {"path": path, "mode": "100644", "type": "blob", "sha": None}
                )

    if not tree:
        return ""

    new_tree = _request(
        "POST", f"/repos/{slug}/git/trees", json={"base_tree": base_tree, "tree": tree}
    )
    commit = _request(
        "POST",
        f"/repos/{slug}/git/commits",
        json={"message": message, "tree": new_tree["sha"], "parents": [head]},
    )
    _request(
        "PATCH", f"/repos/{slug}/git/refs/heads/{ref_name}", json={"sha": commit["sha"]}
    )
    return commit["sha"][:7]
