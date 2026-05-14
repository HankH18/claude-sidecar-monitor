"""HMAC bearer auth for the permission-decision endpoints (V2.D3).

The collector binds to 127.0.0.1 by default and the dashboard reaches
it over the same origin. For the ntfy deep-link path the URL travels
through SMS/push infrastructure though, so it needs a tamper-resistant
token — we sign ``(request_id, exp)`` with the user's ``api_secret``.

Two auth styles:

- **Same-origin bearer**: the dashboard reads ``api_secret`` from a
  server-rendered ``<meta name="csm-token">`` tag in the index.html
  shell and sends it as ``Authorization: Bearer <secret>``. Constant-
  time comparison against the secret in the DB.
- **Signed-deep-link token**: ntfy push URLs include
  ``?t=<base64-hmac>&exp=<unix-ts>``. The token covers ``request_id``
  + ``exp``; the dashboard surfaces the decision modal then attaches
  the bearer for the actual POST.

Both styles route through ``require_bearer`` — a FastAPI dependency
that returns the validated ``api_secret`` if a request is authorised
and raises 401 otherwise.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Any

from fastapi import HTTPException, Request

log = logging.getLogger(__name__)

DEEP_LINK_TTL_SECONDS = 60 * 30  # 30-minute window for ntfy deep-links


def _api_secret(conn: Any) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key='api_secret'").fetchone()
    return row[0] if row else ""


def constant_time_compare(a: str, b: str) -> bool:
    """``hmac.compare_digest`` wrapper that handles empty strings safely.
    Returns False if either side is empty (which is the case when the
    user hasn't run ``csm install`` yet)."""
    if not a or not b:
        return False
    return hmac.compare_digest(a, b)


def sign_deep_link(
    *, request_id: int, api_secret: str, ttl_s: int = DEEP_LINK_TTL_SECONDS
) -> tuple[str, int]:
    """Produce ``(token, exp)`` for embedding in an ntfy push URL.

    The token is base64url-encoded HMAC-SHA256 of ``"<request_id>:<exp>"``.
    The expiry is included as a separate query param so the validator
    can recompute the HMAC and reject expired tokens cheaply.
    """
    exp = int(time.time()) + ttl_s
    msg = f"{request_id}:{exp}".encode()
    digest = hmac.new(api_secret.encode("utf-8"), msg, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return token, exp


def verify_deep_link(*, request_id: int, token: str, exp: int, api_secret: str) -> bool:
    """Constant-time validate a deep-link token. Rejects expired tokens.

    Ordering matters for the timing side-channel: compute the HMAC and
    constant-time compare UNCONDITIONALLY, then AND in the expiry +
    secret checks. That way every failure mode takes the same wall-
    clock time regardless of why it failed (expired vs. wrong signature
    vs. uninstalled), so an attacker can't probe expiry boundaries.
    """
    # Always run the HMAC + compare, even if the secret is empty —
    # using a dummy secret keeps the timing uniform.
    secret = api_secret or "\x00" * 32
    msg = f"{request_id}:{exp}".encode()
    digest = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    expected_token = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    signature_ok = hmac.compare_digest(token, expected_token)

    # Only AFTER the (constant-time) HMAC check do we apply the cheap
    # boolean gates. Using `&` rather than `and` so both expressions
    # are evaluated regardless of order.
    not_expired = int(time.time()) <= exp
    has_secret = bool(api_secret)
    return signature_ok & not_expired & has_secret


def require_bearer(request: Request) -> str:
    """FastAPI dependency: validates the ``Authorization: Bearer ...``
    header against the install's ``api_secret``. Returns the validated
    secret (rarely used; mostly we just check 401 / 200).

    Raises 401 if the header is missing, malformed, or doesn't match.
    Raises 503 if the install has no api_secret yet (csm install hasn't
    run) — distinct status so the dashboard can show a setup banner.
    """
    db = request.app.state.db
    secret = _api_secret(db)
    if not secret:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "api_secret_unset",
                    "message": "Run `csm install` to generate the API secret.",
                }
            },
        )

    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {"code": "missing_bearer", "message": "Authorization header required"}
            },
        )
    presented = header.split(None, 1)[1].strip()
    if not constant_time_compare(secret, presented):
        # Don't log the presented value — it could be near-correct and
        # leak token bytes.
        log.warning("auth: bearer mismatch from %s", request.client.host if request.client else "?")
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "bearer_mismatch", "message": "Invalid bearer token"}},
        )
    return secret
