"""Job leasing primitives.

Lease acquisition, heartbeat refresh, stale-job reaper. Full implementation
lands in the queue-plumbing commit; this module exists so `main.py` and
`tasks.py` have a stable import path.
"""

from __future__ import annotations
