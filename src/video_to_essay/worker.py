"""Worker orchestrator: starts all background worker threads."""

import threading

from .deliver_worker import deliver_loop
from .discover_worker import discover_loop
from .download_worker import download_loop
from .process_worker import process_loop


def start_worker_threads() -> list[threading.Thread]:
    """Start all worker loops in daemon threads."""
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
