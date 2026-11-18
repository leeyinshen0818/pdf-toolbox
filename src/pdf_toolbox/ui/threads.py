from __future__ import annotations

from PySide6.QtCore import QThread


def thread_is_running(thread: QThread | None) -> bool:
    if thread is None:
        return False
    try:
        return thread.isRunning()
    except RuntimeError:
        # The QThread was already deleted via deleteLater after finishing.
        return False
