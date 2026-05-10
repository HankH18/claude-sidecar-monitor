"""``POST /hook/<event>`` FastAPI router."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from csm.hooks.state_machine import (
    KNOWN_EVENTS,
    UnknownEventError,
    apply_event,
)

router = APIRouter()


@router.post("/hook/{event_name}")
async def receive_hook(
    event_name: str, payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Ingest one Claude Code hook event.

    Returns ``{}`` always in v0.1 — the response shape is
    ``permissionDecision``-capable so v2 remote-approval can land
    without changing the wire format.
    """
    if event_name not in KNOWN_EVENTS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "unknown_event",
                    "message": f"unknown hook event: {event_name!r}",
                }
            },
        )

    db = request.app.state.db

    try:
        # apply_event is sync; offload to a thread to avoid blocking
        # the asyncio loop. The state-machine module emits on the bus
        # itself via run_coroutine_threadsafe.
        await asyncio.to_thread(apply_event, db, event_name, payload)
    except UnknownEventError as exc:  # belt-and-suspenders
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "unknown_event", "message": str(exc)}},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_payload", "message": str(exc)}},
        ) from exc

    return {}
