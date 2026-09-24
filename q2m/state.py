"""Runtime state: the status file and the small HTTP status page.

The bridge writes ``status.json`` as it runs and, unless ``--once`` is set,
serves it at http://127.0.0.1:5446/. Nothing here is a data store; it is a
window on the last few events.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 5446
MAX_RECENT = 12

_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>quake2midi</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ background: #0b0b12; color: #d8d8e4; font: 14px/1.5 system-ui,
    sans-serif; margin: 2rem; }}
  h1 {{ font-size: 1.1rem; letter-spacing: .08em; text-transform: uppercase; }}
  .meta {{ color: #7b7b96; margin-bottom: 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 60rem; }}
  th, td {{ text-align: left; padding: .35rem .6rem;
    border-bottom: 1px solid #1e1e2c; }}
  th {{ color: #7b7b96; font-weight: 500; }}
  .mag {{ color: #ff9d5c; font-variant-numeric: tabular-nums; }}
</style>
<h1>quake2midi</h1>
<div class="meta">{meta}</div>
<table>
  <tr><th>time</th><th>mag</th><th>region</th><th>notes</th></tr>
  {rows}
</table>
"""


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class State:
    """The shared, thread-safe view of what the bridge is doing."""

    def __init__(self, root: Path) -> None:
        """Create the state, writing to ``status.json`` under ``root``.

        Args:
            root: The repository root.
        """
        self._path = root / "q2m" / "status.json"
        self._lock = threading.Lock()
        self._data: dict = {
            "started": _now(),
            "updated": _now(),
            "polls": 0,
            "events_total": 0,
            "notes_total": 0,
            "last_error": None,
            "recent": [],
        }

    def _flush_locked(self) -> None:
        """Write ``status.json``. Caller holds the lock."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2)

    def snapshot(self) -> dict:
        """Return a copy of the current state."""
        with self._lock:
            return json.loads(json.dumps(self._data))

    def polled(self) -> None:
        """Record that one poll of the feed happened."""
        with self._lock:
            self._data["polls"] += 1
            self._data["updated"] = _now()
            self._flush_locked()

    def record(self, event: dict, note_count: int) -> None:
        """Record one played event.

        Args:
            event: The event dict that was played.
            note_count: How many notes were sent for it.
        """
        with self._lock:
            self._data["events_total"] += 1
            self._data["notes_total"] += note_count
            self._data["recent"].insert(0, {
                "time": event.get("time"),
                "mag": event.get("mag"),
                "region": event.get("region") or "unknown",
                "lat": event.get("lat"),
                "lon": event.get("lon"),
                "notes": note_count,
                "midi_port": self._data.get("midi_port"),
            })
            del self._data["recent"][MAX_RECENT:]
            self._data["updated"] = _now()
            self._flush_locked()

    def error(self, message: str) -> None:
        """Record a poll error, keeping the loop alive.

        Args:
            message: The error text to store.
        """
        with self._lock:
            self._data["last_error"] = message
            self._data["updated"] = _now()
            self._flush_locked()

    def set_port(self, name: str) -> None:
        """Record the MIDI port in use.

        Args:
            name: The port name, or ``"dry-run"``.
        """
        with self._lock:
            self._data["midi_port"] = name
            self._flush_locked()


def render(state: dict) -> str:
    """Render the status page from a state snapshot.

    Args:
        state: A dict from :meth:`State.snapshot`.

    Returns:
        An HTML document.
    """
    rows = []
    for item in state.get("recent") or []:
        rows.append(
            "<tr>"
            f"<td>{item.get('time') or ''}</td>"
            f"<td class=\"mag\">{item.get('mag')}</td>"
            f"<td>{item.get('region') or ''}</td>"
            f"<td>{item.get('notes')}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan=4>no events yet</td></tr>")
    meta = (
        f"port {state.get('midi_port') or 'not set'} · "
        f"polls {state.get('polls', 0)} · "
        f"events {state.get('events_total', 0)} · "
        f"notes {state.get('notes_total', 0)} · "
        f"updated {state.get('updated', '')}"
    )
    if state.get("last_error"):
        meta += f" · last error: {state['last_error']}"
    return _PAGE.format(meta=meta, rows="\n  ".join(rows))


class StatusServer:
    """A tiny HTTP server that renders :class:`State` at ``/``."""

    def __init__(self, state: State) -> None:
        """Create the server, not yet started.

        Args:
            state: The state to render.
        """
        bound_state = state

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                """Stay quiet; the run loop owns stdout."""
                del fmt, args

            def do_GET(self) -> None:  # noqa: N802 (http.server API)
                """Serve the status page, or 404."""
                if self.path not in ("/", "/index.html"):
                    self.send_response(404)
                    self.end_headers()
                    return
                body = render(bound_state.snapshot()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        self._handler = Handler

    def start(self) -> ThreadingHTTPServer:
        """Start the server on a background thread.

        Returns:
            The running server.

        Raises:
            OSError: The port is already in use.
        """
        server = ThreadingHTTPServer((HOST, PORT), self._handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server