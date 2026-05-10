"""Runtime configuration: paths, env-var overrides, defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


@dataclass(frozen=True)
class Paths:
    """Canonical filesystem locations for csm.

    Each path can be overridden via env var for tests / dev. Production
    defaults follow Apple's Library convention.
    """

    app_support: Path
    db: Path
    salt: Path
    logs: Path
    projects: Path  # Claude Code's JSONL root: ~/.claude/projects
    settings_json: Path  # ~/.claude/settings.json — hooks installed here

    @classmethod
    def from_env(cls) -> Paths:
        app_support = _expand(
            os.environ.get(
                "CSM_APP_SUPPORT",
                "~/Library/Application Support/claude-sidecar-monitor",
            )
        )
        db = _expand(os.environ.get("CSM_DB_PATH", str(app_support / "store.db")))
        salt = _expand(os.environ.get("CSM_SALT_PATH", str(app_support / "store.salt")))
        logs = _expand(os.environ.get("CSM_LOG_DIR", "~/Library/Logs/claude-sidecar-monitor"))
        projects = _expand(os.environ.get("CSM_PROJECTS_DIR", "~/.claude/projects"))
        settings_json = _expand(os.environ.get("CSM_CLAUDE_SETTINGS", "~/.claude/settings.json"))
        return cls(
            app_support=app_support,
            db=db,
            salt=salt,
            logs=logs,
            projects=projects,
            settings_json=settings_json,
        )


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def from_env(cls) -> ServerConfig:
        return cls(
            host=os.environ.get("CSM_HOST", "127.0.0.1"),
            port=int(os.environ.get("CSM_PORT", "8765")),
        )


KEYCHAIN_SERVICE = "claude-sidecar-monitor"


# Default settings seeded into the DB on first migration.
DEFAULT_SETTINGS: dict[str, str] = {
    "hang_yellow_ms": "60000",
    "hang_red_ms": "180000",
    "ntfy_topic": "",
}
