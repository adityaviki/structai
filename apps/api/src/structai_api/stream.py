"""SSE plumbing stub.

Streams from the `event_log` table so clients can resume via `Last-Event-ID`
(plan §7 streaming, §4 invariants). The concrete implementation lands in
Phase 2 alongside the agent loop.
"""

from __future__ import annotations
