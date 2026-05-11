"""Permission-request REST endpoints (V2.D3)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from csm.api.auth import require_bearer
from csm.permissions import record_decision

router = APIRouter()


class PermissionRequestOut(BaseModel):
    id: int
    session_id: str
    tool_use_id: str | None = None
    tool_name: str
    tool_input: Any
    status: str
    decision_reason: str | None = None
    requested_at: str
    decided_at: str | None = None


class PermissionRequestList(BaseModel):
    requests: list[PermissionRequestOut]


class DecisionBody(BaseModel):
    decision: str  # 'allow' | 'deny' | 'ask'
    reason: str | None = None


@router.get(
    "/api/permission-requests",
    response_model=PermissionRequestList,
    dependencies=[Depends(require_bearer)],
)
async def list_permission_requests(
    request: Request,
    status: str = Query(
        "pending",
        pattern="^(pending|allow|deny|ask|expired|timed_out|all)$",
    ),
    limit: int = Query(50, ge=1, le=500),
) -> PermissionRequestList:
    """List permission requests by status. Default is pending — the
    dashboard's banner only ever needs that."""
    db = request.app.state.db

    def _query() -> list[tuple[Any, ...]]:
        if status == "all":
            rows = db.execute(
                "SELECT id, session_id, tool_use_id, tool_name, tool_input_json, "
                "status, decision_reason, requested_at, decided_at "
                "FROM permission_requests ORDER BY requested_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id, session_id, tool_use_id, tool_name, tool_input_json, "
                "status, decision_reason, requested_at, decided_at "
                "FROM permission_requests WHERE status = ? "
                "ORDER BY requested_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return list(rows)

    rows = await asyncio.to_thread(_query)
    out: list[PermissionRequestOut] = []
    for r in rows:
        try:
            tool_input = json.loads(r[4]) if r[4] else None
        except json.JSONDecodeError:
            tool_input = r[4]
        out.append(
            PermissionRequestOut(
                id=r[0],
                session_id=r[1],
                tool_use_id=r[2],
                tool_name=r[3],
                tool_input=tool_input,
                status=r[5],
                decision_reason=r[6],
                requested_at=r[7],
                decided_at=r[8],
            )
        )
    return PermissionRequestList(requests=out)


@router.post(
    "/api/permission-requests/{request_id}/decide",
    response_model=PermissionRequestOut,
    dependencies=[Depends(require_bearer)],
)
async def decide_permission_request(
    request_id: int, body: DecisionBody, request: Request
) -> PermissionRequestOut:
    """Submit a decision. Idempotent: re-deciding a non-pending row
    returns 409 Conflict so the dashboard can show "expired" cleanly."""
    db = request.app.state.db
    if body.decision not in ("allow", "deny", "ask"):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_decision", "message": body.decision}},
        )

    accepted = await record_decision(
        db,
        request_id=request_id,
        decision=body.decision,
        reason=body.reason,
    )
    if not accepted:
        # Either the row doesn't exist or it's already in a terminal state.
        def _peek() -> tuple[Any, ...] | None:
            row = db.execute(
                "SELECT status FROM permission_requests WHERE id = ?", (request_id,)
            ).fetchone()
            return tuple(row) if row is not None else None

        existing = await asyncio.to_thread(_peek)
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": str(request_id)}},
            )
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "already_decided",
                    "message": f"request already {existing[0]}",
                }
            },
        )

    # Return the updated row.
    def _read() -> tuple[Any, ...] | None:
        row = db.execute(
            "SELECT id, session_id, tool_use_id, tool_name, tool_input_json, "
            "status, decision_reason, requested_at, decided_at "
            "FROM permission_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        return tuple(row) if row is not None else None

    row = await asyncio.to_thread(_read)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found"}})

    try:
        tool_input = json.loads(row[4]) if row[4] else None
    except json.JSONDecodeError:
        tool_input = row[4]
    return PermissionRequestOut(
        id=row[0],
        session_id=row[1],
        tool_use_id=row[2],
        tool_name=row[3],
        tool_input=tool_input,
        status=row[5],
        decision_reason=row[6],
        requested_at=row[7],
        decided_at=row[8],
    )
