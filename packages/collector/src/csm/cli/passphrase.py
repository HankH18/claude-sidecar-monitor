"""``csm change-passphrase`` — atomic passphrase rotation."""

from __future__ import annotations

import sqlcipher3
import typer

from csm import crypto
from csm.config import Paths
from csm.crypto import MIN_PASSPHRASE_LEN


def change_passphrase_command() -> None:
    """Rotate the at-rest encryption passphrase.

    The new passphrase is confirmed; the old passphrase is required to
    open the existing DB. ``crypto.rotate_passphrase`` performs the
    SQLCipher ``PRAGMA rekey`` atomically and updates the Keychain entry.
    """
    paths = Paths.from_env()

    typer.echo("Rotating passphrase. The DB is rekeyed atomically.")
    old_passphrase = typer.prompt("Current passphrase", hide_input=True)
    new_passphrase = typer.prompt(
        "New passphrase",
        hide_input=True,
        confirmation_prompt=True,
    )
    if len(new_passphrase) < MIN_PASSPHRASE_LEN:
        typer.echo(
            f"Error: new passphrase must be at least {MIN_PASSPHRASE_LEN} characters.",
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        crypto.rotate_passphrase(
            old_passphrase,
            new_passphrase,
            salt_path=paths.salt,
            db_path=paths.db,
        )
    except sqlcipher3.DatabaseError:
        typer.echo("Error: current passphrase is wrong (DB failed to open).", err=True)
        raise typer.Exit(code=1) from None

    typer.echo("Passphrase rotated. Keychain entry updated.")
