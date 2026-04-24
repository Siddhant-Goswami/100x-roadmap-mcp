"""
Git-backed storage for the pilot data repo.

Every write is a git commit. Reads are cached in-memory until a write
to the same path invalidates the entry. No push — the MVP is local-only;
the mentor can `git push` manually or a cron can do it later.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

PILOT_REPO = Path(os.environ.get(
    "PILOT_REPO_PATH",
    os.path.expanduser("~/projects/100x/medianmirror-pilot"),
))

_cache: dict[str, str] = {}


def _abs(relpath: str) -> Path:
    p = (PILOT_REPO / relpath).resolve()
    if PILOT_REPO.resolve() not in p.parents and p != PILOT_REPO.resolve():
        raise ValueError(f"path escapes pilot repo: {relpath}")
    return p


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(PILOT_REPO), *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def read_file(relpath: str) -> str:
    if relpath in _cache:
        return _cache[relpath]
    path = _abs(relpath)
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    _cache[relpath] = text
    return text


def write_file(relpath: str, content: str, commit_msg: str, author: str) -> None:
    """author is 'role:id' e.g. 'mentor:riya' or 'mentee:arjun'."""
    path = _abs(relpath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _cache[relpath] = content
    _commit(relpath, commit_msg, author)


def append_file(relpath: str, content: str, commit_msg: str, author: str) -> None:
    existing = read_file(relpath)
    if existing and not existing.endswith("\n"):
        existing += "\n"
    write_file(relpath, existing + content, commit_msg, author)


def _commit(relpath: str, msg: str, author: str) -> None:
    _git("add", relpath)
    # Skip if nothing staged
    status = _git("status", "--porcelain", relpath).strip()
    if not status:
        return
    role, _, ident = author.partition(":")
    name = f"{role}-{ident}" if ident else role or "pilot"
    email = f"{name}@medianmirror.local"
    _git(
        "-c", f"user.name={name}",
        "-c", f"user.email={email}",
        "commit", "-q", "-m", msg,
    )


def list_mentees() -> list[str]:
    mentees_dir = PILOT_REPO / "mentees"
    if not mentees_dir.exists():
        return []
    return sorted(p.name for p in mentees_dir.iterdir() if p.is_dir())
