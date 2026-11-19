from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Slot


def thread_is_running(thread: QThread | None) -> bool:
    if thread is None:
        return False
    try:
        return thread.isRunning()
    except RuntimeError:
        # The QThread was already deleted via deleteLater after finishing.
        return False


class _ThreadKeeper(QObject):
    """Holds unparented worker threads until they finish.

    Deleting a running QThread aborts the process, so a page that is cleared, closed or destroyed
    mid-job only asks its worker to stop; the thread and worker are released here (on the GUI
    thread, via a queued connection) once the thread has really finished.
    """

    def __init__(self) -> None:
        super().__init__()
        self._live: dict[QThread, QObject] = {}

    def keep(self, thread: QThread, worker: QObject) -> None:
        self._live[thread] = worker
        thread.finished.connect(self._release)

    @Slot()
    def _release(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread) or thread not in self._live:
            return
        thread.wait()  # `finished` is emitted just before the OS thread exits
        self._live.pop(thread)

    def running_count(self) -> int:
        return sum(1 for thread in self._live if thread_is_running(thread))


_keeper: _ThreadKeeper | None = None


def _thread_keeper() -> _ThreadKeeper:
    global _keeper
    if _keeper is None:
        _keeper = _ThreadKeeper()  # created on first use, on the GUI thread
    return _keeper


def keep_alive_until_finished(thread: QThread, worker: QObject) -> None:
    """Keep an unparented `thread` and its `worker` alive until the thread has finished."""
    _thread_keeper().keep(thread, worker)


def live_thread_count() -> int:
    """Worker threads registered with keep_alive_until_finished that are still running."""
    return _thread_keeper().running_count()
