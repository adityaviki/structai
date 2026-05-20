"""Job queue primitives (plan §4).

The queue is Postgres-backed (no Redis dep). The API enqueues via
`queue.enqueue`; the worker polls via `queue.claim_one`, heartbeats via
`queue.heartbeat`, and finalizes via `queue.complete` / `queue.fail` /
`queue.cancel`. The reaper recycles jobs whose lease has expired.

A retryable failure with attempts remaining returns the job to `queued`
for another claim; otherwise (terminal failure, or retryable but out of
attempts) the job stays `failed`. Idempotency keys deduplicate enqueues.
"""

from structai_core.jobs.cancellation import CancellationToken
from structai_core.jobs.errors import JobError, RetryableError, TerminalError
from structai_core.jobs.queue import JobClaim

__all__ = [
    "CancellationToken",
    "JobClaim",
    "JobError",
    "RetryableError",
    "TerminalError",
]
