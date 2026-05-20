"""Worker entrypoint.

Polls `jobs` with `FOR UPDATE SKIP LOCKED`, leases a job, dispatches via
`tasks.py`, heartbeats while running, releases on completion. The full
queue plumbing lands in the next commit; this is the boot scaffold so the
process starts under `make dev` today.
"""

from __future__ import annotations

import asyncio
import logging
import signal

log = logging.getLogger("structai_worker")


async def run() -> None:
    log.info("worker booted; queue plumbing arrives in the next commit")
    stop = asyncio.Event()

    def _stop(*_: object) -> None:
        log.info("shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _stop)

    await stop.wait()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
