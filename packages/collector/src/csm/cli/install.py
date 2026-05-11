"""``csm install`` and ``csm uninstall`` orchestrators.

``install`` walks the user through:

1. Passphrase prompt (with confirmation).
2. ``crypto.first_run_setup`` — derive Argon2id key, persist salt at
   ``~/Library/Application Support/claude-sidecar-monitor/store.salt``,
   cache the raw key in macOS Keychain.
3. ``install_hooks`` — merge entries into ``~/.claude/settings.json``
   (idempotent, with timestamped backup).
4. ``install_launchd`` — render the LaunchAgent plist into
   ``~/Library/LaunchAgents/`` and best-effort ``launchctl bootstrap``.
5. ntfy topic prompt (optional). Stored in ``settings`` table.
6. Print the dashboard URL hint (Tailscale Serve setup is per-user and
   handled separately per spec §10).

Each step has an opt-out flag so the user can re-run a single step
without re-prompting for passphrase / overwriting unrelated state.
"""

from __future__ import annotations

import shutil

import typer

from csm import crypto
from csm.cli.hooks import install_hooks
from csm.cli.launchd import plist_install_path, uninstall_launchd
from csm.config import Paths
from csm.crypto import MIN_PASSPHRASE_LEN
from csm.db import connect


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

    # Step 1 — passphrase + key cache
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
    if not dry_run:
        crypto.first_run_setup(passphrase, paths.salt)
        typer.echo(f"Derived key cached in Keychain (salt at {paths.salt}).")
    else:
        typer.echo("[dry-run] would derive key + cache in Keychain.")

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
        # We need the just-derived key to open the DB. Pull from Keychain
        # rather than holding the raw bytes around in this scope.
        key = crypto.get_key_from_keychain()
        if key is None:
            typer.echo("WARNING: key not found in Keychain — skipping ntfy_topic write.")
        else:
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
