from __future__ import annotations

import logging
import os
import threading

from app.runtime import AutomationRuntime
from app.updater import UpdateWatcher, relaunch, repo_root
from app.utils.logging import setup_logging

logger = logging.getLogger("application")


def main() -> None:
    setup_logging()
    runtime = AutomationRuntime()
    restart = threading.Event()
    watcher = UpdateWatcher(on_restart=restart.set)
    runtime.start()
    watcher.start()
    thread = runtime._thread
    try:
        if thread is not None:
            while thread.is_alive() and not restart.is_set():
                thread.join(timeout=0.4)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
        watcher.stop()
        runtime.stop()
        return
    if not restart.is_set():
        watcher.stop()
        return
    watcher.stop()
    runtime.stop()
    root = repo_root()
    if root is not None:
        relaunch("app.main", root)
    os._exit(0)


if __name__ == "__main__":
    main()
