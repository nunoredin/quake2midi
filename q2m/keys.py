"""Read single keypresses from the terminal.

The bridge watches for the spacebar so a fake event can be triggered by
hand. Reading a key without waiting for Enter means putting the terminal
into cbreak mode, which has to be undone before the process exits or the
user's shell is left in a broken state.
"""

from __future__ import annotations

import atexit
import os
import queue
import signal
import sys
import threading

try:
    import termios
    import tty
except ImportError:  # Windows
    termios = None
    tty = None

try:
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None

_POLL_S = 0.2
# Signals that end the process without unwinding the stack, so the terminal
# would be left in cbreak mode (no echo, no line editing) unless we catch
# them. SIGINT is absent on purpose: it raises KeyboardInterrupt, which the
# run loop already handles.
_FATAL_SIGNALS = ("SIGTERM", "SIGHUP")


class KeyWatcher:
    """Deliver single keypresses from the terminal to the run loop.

    Keys are read on a background thread and queued, so the loop can wait
    on :meth:`get` with a timeout and wake the moment a key arrives.
    """

    def __init__(self) -> None:
        """Create the watcher. Call :meth:`start` to begin reading."""
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fd: int | None = None
        self._saved: list | None = None
        self._prev_handlers: dict[int, object] = {}

    @staticmethod
    def supported() -> bool:
        """Return True if this platform can read single keys."""
        return termios is not None or msvcrt is not None

    def start(self) -> bool:
        """Begin reading keys.

        Returns:
            True if the watcher started. False if the platform is
            unsupported or stdin is not a terminal, in which case there is
            nothing to read and the caller should carry on without it.
        """
        if not self.supported() or not sys.stdin.isatty():
            return False
        if termios is not None:
            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
            self._install_guards()
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()
        return True

    def _install_guards(self) -> None:
        """Arrange for the terminal to be restored on any exit path.

        ``finally`` covers a normal stop and Ctrl+C, but not a signal that
        kills the process outright. Without these, closing the window or
        killing the bridge would leave the shell with no echo.
        """
        atexit.register(self.restore)
        for name in _FATAL_SIGNALS:
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                self._prev_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, self._on_fatal_signal)
            except (ValueError, OSError):
                # Not on the main thread, or unsupported: atexit still helps.
                continue

    def _on_fatal_signal(self, signum: int, frame: object) -> None:
        """Restore the terminal, then die the way the signal intended."""
        del frame
        self.restore()
        previous = self._prev_handlers.get(signum)
        if callable(previous):
            previous(signum, None)
            return
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    def _remove_guards(self) -> None:
        """Undo :meth:`_install_guards`."""
        for sig, previous in self._prev_handlers.items():
            try:
                signal.signal(sig, previous)
            except (ValueError, OSError, TypeError):
                continue
        self._prev_handlers.clear()

    def stop(self) -> None:
        """Stop reading and restore the terminal."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.restore()
        self._remove_guards()

    def restore(self) -> None:
        """Put the terminal back the way it was, if it was changed.

        Safe to call more than once, and safe to call when the watcher
        never started.
        """
        if self._fd is None or self._saved is None:
            return
        try:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
        except (termios.error, OSError):
            pass
        self._saved = None

    def get(self, timeout: float) -> str | None:
        """Return the next key, or None if none arrived in time.

        Args:
            timeout: Seconds to wait.

        Returns:
            One character, or None on timeout.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _read(self) -> None:
        """Read keys until stopped. Runs on the background thread."""
        if msvcrt is not None:
            self._read_windows()
        else:
            self._read_posix()

    def _read_posix(self) -> None:
        """Read keys with select, so :meth:`stop` is noticed promptly."""
        import select

        while not self._stop.is_set():
            ready, _, _ = select.select([self._fd], [], [], _POLL_S)
            if not ready:
                continue
            try:
                data = os.read(self._fd, 1)
            except OSError:
                return
            if not data:
                return
            self._queue.put(data.decode("utf-8", "replace"))

    def _read_windows(self) -> None:
        """Read keys by polling ``msvcrt``."""
        import time

        while not self._stop.is_set():
            if msvcrt.kbhit():
                self._queue.put(msvcrt.getwch())
            else:
                time.sleep(_POLL_S)
