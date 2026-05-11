"""``csm purge`` — retention controls + reset.

Two modes, mutually exclusive:

- ``--older-than <duration>`` deletes ``events`` and ``transcript_messages``
  older than the given duration. Sessions themselves are kept (they're the
  primary key everything FKs against). Duration grammar: ``<int><unit>``
  where unit is one of ``s/m/h/d/w``.
- ``--reset-passphrase`` wipes the DB + salt + Keychain entry. This forces
  a fresh ``csm install`` on next run. Confirmed via prompt.
"""

from __future__ import annotations

import re
import shutil
from datetime import UTC, datetime, timedelta

import typer

from csm import crypto
from csm.config import Paths
from csm.db import connect

_DURATION_RE = re.compile(r"^(?P<n>\d+)(?P<unit>[smhdw])$")
_UNIT_SECS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
}


def parse_duration(s: str) -> timedelta:
    """Parse strings like ``30d``, ``24h``, ``90m``, ``2w``.

    Raises :class:`ValueError` on invalid input.
    """
    m = _DURATION_RE.match(s.strip())
    if m is None:
        raise ValueError(f"invalid duration {s!r}: expected <int><unit> where unit is s/m/h/d/w")
    n = int(m.group("n"))
    unit = m.group("unit")
    return timedelta(seconds=n * _UNIT_SECS[unit])


def _delete_older_than(*, duration: timedelta, key: bytes | None) -> tuple[int, int]:
    """Delete events + transcript messages older than ``duration``.

    Returns ``(events_deleted, transcripts_deleted)``.
    """
    paths = Paths.from_env()
    cutoff = (datetime.now(tz=UTC) - duration).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = connect(key=key, db_path=paths.db)
    try:
        cur = conn.execute("DELETE FROM events WHERE received_at < ?", (cutoff,))
        events_n = cur.rowcount
        cur = conn.execute("DELETE FROM transcript_messages WHERE timestamp < ?", (cutoff,))
        transcripts_n = cur.rowcount
    finally:
        conn.close()
    return events_n, transcripts_n


def _reset_everything() -> None:
    """Wipe DB, salt, and Keychain entry."""
    paths = Paths.from_env()
    crypto.delete_key_from_keychain()
    if paths.db.exists():
        paths.db.unlink()
    # SQLite WAL/SHM siblings
    for sibling in (
        paths.db.with_suffix(paths.db.suffix + "-wal"),
        paths.db.with_suffix(paths.db.suffix + "-shm"),
    ):
        if sibling.exists():
            sibling.unlink()
    if paths.salt.exists():
        paths.salt.unlink()
    if paths.app_support.exists() and not any(paths.app_support.iterdir()):
        shutil.rmtree(paths.app_support)


def purge_command(
    older_than: str | None = typer.Option(
        None, "--older-than", help="Delete events/transcripts older than e.g. 30d, 24h."
    ),
    reset_passphrase: bool = typer.Option(
        False, "--reset-passphrase", help="Wipe DB + salt + Keychain. Forces fresh install."
    ),
) -> None:
    """Prune the local store or wipe it entirely.

    Exactly one of ``--older-than`` or ``--reset-passphrase`` must be set.
    """
    if older_than and reset_passphrase:
        typer.echo(
            "Error: --older-than and --reset-passphrase are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=2)
    if not older_than and not reset_passphrase:
        typer.echo("csm purge needs one of:", err=True)
        typer.echo(
            "  --older-than <duration>   delete events/transcripts older than the duration",
            err=True,
        )
        typer.echo(
            "                            (units: s, m, h, d, w — e.g. 30d, 24h, 2w)",
            err=True,
        )
        typer.echo(
            "  --reset-passphrase        wipe DB + salt + Keychain entry; forces fresh install",
            err=True,
        )
        typer.echo("", err=True)
        typer.echo("Run `csm purge --help` for full options.", err=True)
        raise typer.Exit(code=2)

    if reset_passphrase:
        confirm = typer.confirm(
            "This will DELETE the encrypted DB, salt, and Keychain key. Continue?",
            default=False,
        )
        if not confirm:
            typer.echo("Aborted.")
            raise typer.Exit(code=1)
        _reset_everything()
        typer.echo("Reset complete. Run `csm install` to set up again.")
        return

    assert older_than is not None  # narrow for type-checker
    try:
        duration = parse_duration(older_than)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from None

    key = crypto.get_key_from_keychain()
    events_n, transcripts_n = _delete_older_than(duration=duration, key=key)
    typer.echo(
        f"Purged {events_n} events and {transcripts_n} transcript messages older than {older_than}."
    )
