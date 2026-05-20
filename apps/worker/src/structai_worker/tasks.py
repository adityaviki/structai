"""Worker task dispatch.

Each `jobs.kind` value maps to a callable that runs inside a leased job.
Phase 1+ wire `profile_file`, `run_agent_session`, `execute_pipeline`
(plan §10).
"""

from __future__ import annotations
