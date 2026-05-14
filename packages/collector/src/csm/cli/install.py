"""``csm install`` and ``csm uninstall`` orchestrators.

``install`` walks the user through:

1. Passphrase setup — three paths depending on existing state:
   a. First-run (no Keychain entry): prompt + ``crypto.first_run_setup``.
   b. Re-install (Keychain entry opens DB): skip the passphrase prompt,
      reuse the cached key.
   c. Recovery (Keychain entry present but does NOT open DB): warn,
      offer to re-enter the original passphrase, derive + verify before
      touching the Keychain. NEVER blindly overwrite a Keychain entry
      we know is mismatched against the DB — that path stranded users
      on encrypted data they couldn't decrypt.
2. ``install_hooks`` — merge entries into ``~/.claude/settings.json``
   (idempotent, with timestamped backup).
3. ``install_launchd`` — render the LaunchAgent plist into
   ``~/Library/LaunchAgents/`` and best-effort ``launchctl bootstrap``.
4. ntfy topic prompt (optional). Stored in ``settings`` table.
5. Print the dashboard URL hint (Tailscale Serve setup is per-user and
   handled separately per spec §10).

Each step has an opt-out flag so the user can re-run a single step
without re-prompting for passphrase / overwriting unrelated state.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer

from csm import crypto
from csm.cli.hooks import install_hooks
from csm.cli.launchd import plist_install_path, uninstall_launchd
from csm.config import Paths
from csm.crypto import MIN_PASSPHRASE_LEN
from csm.db import connect

# Max attempts at recovery before bailing out and pointing the user at
# `csm purge --reset-passphrase`. Three matches the macOS Keychain prompt
# UX they're already conditioned to.
_RECOVERY_MAX_ATTEMPTS = 3


def _set_ntfy_topic(topic: str, *, key: bytes) -> None:
    """Write ``settings.ntfy_topic`` directly via the DB layer."""
    paths = Paths.from_env()
    conn = connect(key=key, db_path=paths.db)
    try:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
            ("ntfy_topic", topic),
        )
    finally:
        conn.close()


def _can_open_db(key: bytes, db_path: Path) -> bool:
    """Return True if ``key`` decrypts the DB at ``db_path``.

    Any failure — missing file, wrong key, corrupted header — is treated
    uniformly as "can't open." The caller routes the user accordingly.
    """
    if not db_path.exists():
        return False
    try:
        conn = connect(key=key, db_path=db_path)
    except Exception:
        return False
    try:
        # SQLCipher returns garbage rows on a wrong key until a real read
        # forces decrypt — connect() already does that, so we just close.
        conn.close()
    except Exception:
        return False
    return True


def _prompt_new_passphrase() -> str:
    """Prompt for a fresh passphrase with confirmation + length check."""
    passphrase = typer.prompt(
        "Choose a passphrase to encrypt the local store",
        hide_input=True,
        confirmation_prompt=True,
    )
    if len(passphrase) < MIN_PASSPHRASE_LEN:
        typer.echo(
            f"Error: passphrase must be at least {MIN_PASSPHRASE_LEN} characters "
            "(empty/short passphrases give false confidence — the store would "
            "be trivially brute-forceable).",
            err=True,
        )
        raise typer.Exit(code=2)
    return str(passphrase)


def _recover_existing_db(paths: Paths) -> bytes:
    """Recovery path: existing DB present but cached Keychain key doesn't open it.

    Up to _RECOVERY_MAX_ATTEMPTS prompts. On a correct passphrase, the
    derived key is verified against the DB BEFORE touching the Keychain
    — so a wrong guess never strands the user further.
    """
    typer.echo("")
    typer.echo("WARNING: a cached Keychain key is present but does NOT decrypt the existing DB.")
    typer.echo(f"  DB path:   {paths.db}")
    typer.echo(f"  Salt path: {paths.salt}")
    typer.echo("This usually means a previous `csm install` was run with a different passphrase.")
    typer.echo("")
    typer.echo("Options:")
    typer.echo("  1. Re-enter your ORIGINAL passphrase to recover (the data is recoverable).")
    typer.echo("  2. Abort and run `csm purge --reset-passphrase` to wipe and start fresh.")
    typer.echo("")
    if not typer.confirm("Re-enter original passphrase now?", default=True):
        typer.echo("Aborted. Run `csm purge --reset-passphrase` to wipe the store.")
        raise typer.Exit(code=1)

    salt = crypto.load_or_create_salt(paths.salt)
    for attempt in range(_RECOVERY_MAX_ATTEMPTS):
        passphrase = typer.prompt(
            "Enter original passphrase",
            hide_input=True,
        )
        if len(passphrase) < MIN_PASSPHRASE_LEN:
            remaining = _RECOVERY_MAX_ATTEMPTS - attempt - 1
            typer.echo(f"  Too short. {remaining} attempts remaining.", err=True)
            continue
        derived = crypto.derive_key(passphrase, salt)
        if _can_open_db(derived, paths.db):
            crypto.store_key_in_keychain(derived)
            typer.echo("Recovered: derived key from original passphrase, cached in Keychain.")
            return derived
        remaining = _RECOVERY_MAX_ATTEMPTS - attempt - 1
        if remaining > 0:
            typer.echo(f"  Wrong passphrase. {remaining} attempts remaining.", err=True)

    typer.echo(
        "Recovery failed. Run `csm purge --reset-passphrase` to wipe the store and start over.",
        err=True,
    )
    raise typer.Exit(code=1)


def _setup_or_reuse_key(paths: Paths) -> bytes:
    """Resolve the encryption key for this install.

    Routes to one of three paths based on the current state of the
    Keychain entry and the on-disk DB. Always returns a key that
    actually opens the DB (or raises Exit). Never overwrites a working
    Keychain entry.
    """
    existing = crypto.get_key_from_keychain()
    db_exists = paths.db.exists()

    if existing is not None and db_exists:
        if _can_open_db(existing, paths.db):
            typer.echo("Encryption key: already cached and opens existing DB — reusing.")
            return existing
        return _recover_existing_db(paths)

    if existing is not None and not db_exists:
        # Stale Keychain entry from a previous install whose DB was
        # deleted out-of-band. Clear it and treat as first-run so the
        # user gets a fresh passphrase prompt without surprise.
        typer.echo("Keychain entry present but DB is missing — clearing stale entry.")
        crypto.delete_key_from_keychain()

    passphrase = _prompt_new_passphrase()
    crypto.first_run_setup(passphrase, paths.salt)
    typer.echo(f"Derived key cached in Keychain (salt at {paths.salt}).")
    key = crypto.get_key_from_keychain()
    assert key is not None  # just stored — narrow for type-checker
    return key


def install_command(
    no_hooks: bool = typer.Option(False, "--no-hooks", help="Skip ~/.claude/settings.json merge."),
    no_launchd: bool = typer.Option(
        False, "--no-launchd", help="Skip LaunchAgent install + bootstrap."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without writing."),
) -> None:
    """One-command first-run bootstrap.

    Steps:
      1. Prompt for passphrase, derive + cache key.
      2. (unless ``--no-hooks``) merge into ~/.claude/settings.json.
      3. (unless ``--no-launchd``) install + bootstrap LaunchAgent.
      4. Prompt for ntfy topic (optional, empty = disabled).
      5. Print dashboard URL hint.
    """
    paths = Paths.from_env()

    typer.echo("csm install — first-run bootstrap")
    typer.echo("================================")

    # Step 1 — passphrase + key cache. Routes between first-run, reuse,
    # and recovery based on what's already in the Keychain + on disk.
    if not dry_run:
        key = _setup_or_reuse_key(paths)
        # V2.D — generate (and persist) a 32-byte api_secret for the
        # permission-decision endpoint's HMAC bearer. Idempotent: only
        # writes when the existing value is empty so a re-install keeps
        # any previously-issued dashboard tokens working.
        import secrets

        conn = connect(key=key, db_path=paths.db)
        try:
            current = conn.execute("SELECT value FROM settings WHERE key='api_secret'").fetchone()
            if current is None or not current[0]:
                api_secret = secrets.token_urlsafe(32)
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES ('api_secret', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                    "updated_at=datetime('now')",
                    (api_secret,),
                )
                typer.echo("API secret: generated.")
            else:
                typer.echo("API secret: already present (kept existing).")
        finally:
            conn.close()
    else:
        typer.echo("[dry-run] would derive key + cache in Keychain.")
        typer.echo("[dry-run] would generate api_secret in settings DB.")

    # Step 2 — hooks
    if not no_hooks:
        result = install_hooks(dry_run=dry_run)
        if not result.changed:
            typer.echo(f"Hooks: already up to date at {result.settings_path}.")
        elif dry_run:
            typer.echo(f"[dry-run] would update {result.settings_path}.")
        else:
            if result.backup_path is not None:
                typer.echo(f"Hooks: backed up existing settings to {result.backup_path}.")
            typer.echo(f"Hooks: installed into {result.settings_path}.")
    else:
        typer.echo("Hooks: skipped (--no-hooks).")

    # Step 3 — launchd
    if not no_launchd:
        if dry_run:
            typer.echo(f"[dry-run] would write LaunchAgent plist to {plist_install_path()}.")
        else:
            # Imported lazily so a no-launchd install doesn't pay the
            # subprocess import cost.
            from csm.cli.launchd import install_launchd

            ld = install_launchd()
            typer.echo(f"LaunchAgent: wrote {ld.plist_path}.")
            if ld.bootstrap_ok:
                typer.echo("LaunchAgent: launchctl bootstrap ok.")
            else:
                typer.echo(f"LaunchAgent: launchctl bootstrap failed ({ld.bootstrap_message}).")
                typer.echo(f"  Run manually: {ld.manual_command}")
    else:
        typer.echo("LaunchAgent: skipped (--no-launchd).")

    # Step 4 — ntfy topic
    topic = typer.prompt(
        "ntfy topic for push notifications (leave empty to disable)",
        default="",
        show_default=False,
    )
    if not dry_run:
        # ``key`` was bound by _setup_or_reuse_key above and known to open
        # the DB. Reuse it directly — no extra Keychain round-trip.
        _set_ntfy_topic(topic, key=key)
        if topic:
            typer.echo(f"ntfy topic set: {topic}")
        else:
            typer.echo("ntfy topic disabled (empty).")
    else:
        typer.echo(f"[dry-run] would set ntfy_topic={topic!r} in settings DB.")

    # Step 5 — closing message
    typer.echo("")
    typer.echo("Done. Dashboard hint:")
    typer.echo("  Locally: http://127.0.0.1:8765/")
    typer.echo("  Tailnet: configure `tailscale serve` separately (see docs/spec.md §10).")


def uninstall_command(
    purge: bool = typer.Option(
        False,
        "--purge",
        help="Also delete Keychain key + ~/Library/Application Support/claude-sidecar-monitor/.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt (for scripted use).",
    ),
) -> None:
    """Reverse of ``csm install`` — remove hooks + LaunchAgent.

    With ``--purge``, additionally wipe the Keychain entry and the
    application-support directory (DB, salt, etc.). Confirmed via prompt
    because that step is irreversible.

    Even without ``--purge``, an unprompted uninstall is undesirable
    (mid-shell typo on ``csm install`` lands on uninstall mid-command
    completion) so we gate the plain path behind a confirmation too.
    Pass ``--yes`` to skip — useful in test fixtures and scripts.
    """
    typer.echo("csm uninstall")
    typer.echo("=============")

    if not yes:
        msg = (
            "This will remove csm hooks from ~/.claude/settings.json and "
            "unload the LaunchAgent. Continue?"
        )
        if purge:
            msg = (
                "This will remove csm hooks, unload the LaunchAgent, "
                "AND with --purge wipe the encrypted DB + Keychain entry. Continue?"
            )
        if not typer.confirm(msg, default=False):
            typer.echo("Aborted.")
            raise typer.Exit(code=0)

    # Hooks — uninstall preserves any non-csm entries.
    result = install_hooks(uninstall=True)
    if result.changed:
        if result.backup_path is not None:
            typer.echo(f"Hooks: backed up existing settings to {result.backup_path}.")
        typer.echo(f"Hooks: removed csm entries from {result.settings_path}.")
    else:
        typer.echo("Hooks: nothing to remove.")

    # LaunchAgent
    removed, msg = uninstall_launchd()
    typer.echo(f"LaunchAgent: bootout={msg}; removed={removed}.")

    if not purge:
        typer.echo("Done. (Use --purge to also wipe Keychain key + DB.)")
        return

    # Purge — second confirmation since this step is irreversible.
    # Bypass when --yes is set (the top-of-function confirm already
    # acknowledged the purge intent in that case).
    if not yes:
        confirm = typer.confirm(
            "PURGE will delete the encrypted DB, salt, and Keychain key. "
            "This is irreversible. Continue?",
            default=False,
        )
        if not confirm:
            typer.echo("Aborted purge.")
            return

    crypto.delete_key_from_keychain()
    typer.echo("Keychain entry: removed.")

    paths = Paths.from_env()
    if paths.app_support.exists():
        shutil.rmtree(paths.app_support)
        typer.echo(f"App support dir removed: {paths.app_support}")
    else:
        typer.echo("App support dir: nothing to remove.")
