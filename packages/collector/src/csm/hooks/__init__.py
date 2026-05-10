"""Claude Code lifecycle hook receiver (T6).

The collector's primary low-latency ingestion path. Each hook fired by
``claude`` becomes a ``POST /hook/<event>`` to this router. Events go
through ``state_machine.apply_event`` which:

1. Validates the event name.
2. Server-side timestamps it.
3. Inserts into ``events``.
4. Updates the ``sessions`` row's state machine.
5. Emits a ``BusEvent`` on the in-process bus for SSE/aggregator
   subscribers.
6. Returns a ``permissionDecision``-shaped response (always ``{}`` in
   v0.1) so the contract is v2-ready without changes later.

The state machine + DB writes are pure-sync; the FastAPI handler offloads
them to a thread pool to keep the event loop responsive.
"""

from __future__ import annotations

from csm.hooks.receiver import router

__all__ = ["router"]
