"""Resolve a session's worktree root from its ``cwd``.

Walks up from the given path looking for a ``.git`` directory or file
(file = git worktree). If none is found, falls back to the cwd itself.

Cached per-cwd so repeated lookups during a session are cheap.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=512)
def resolve_worktree(cwd: str) -> str:
    """Return the worktree root for ``cwd`` as an absolute path string."""
    path = Path(cwd).resolve()
    for ancestor in (path, *path.parents):
        if (ancestor / ".git").exists():
            return str(ancestor)
    return str(path)


def project_label(worktree_root: str) -> str:
    """Human-readable project label = the worktree root's directory name."""
    return Path(worktree_root).name or worktree_root
