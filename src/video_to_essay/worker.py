"""Worker orchestrator: starts all background worker threads."""

import logging
import os
import threading

import sentry_sdk

from .deliver_worker import deliver_loop
from .discover_worker import discover_loop
from .download_worker import download_loop
from .process_worker import process_loop


_sentry_initialized = False


def init_sentry() -> None:
    """Initialize Sentry SDK if SENTRY_DSN is set. Safe to call multiple times."""
    global _sentry_initialized
    if _sentry_initialized:
        return
    sentry_dsn = os.environ.get("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            traces_sample_rate=1.0,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        )
    _sentry_initialized = True


def start_worker_threads() -> list[threading.Thread]:
    """Start all worker loops in daemon threads."""
    init_sentry()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    workers = [
        ("discover", discover_loop, 60.0),
        ("download", download_loop, 10.0),
        ("process", process_loop, 10.0),
        ("deliver", deliver_loop, 15.0),
    ]
    threads = []
    for name, loop_fn, interval in workers:
        t = threading.Thread(target=loop_fn, args=(interval,), daemon=True, name=name)
        t.start()
        threads.append(t)
    return threads
