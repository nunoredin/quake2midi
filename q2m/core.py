"""The bridge: poll the feed, map events, send MIDI.

The loop is deliberately small. Each tick fetches the recent events at or
above the magnitude floor, skips any id already seen this run, maps the rest
to notes, and plays them through the sink. Failures in a fetch are recorded
and retried; they never kill the loop.
"""

from __future__ import annotations

import sys
import time

import mido

from q2m import mapping, quakes
from q2m.state import State

POLL_INTERVAL_S = 8.0
DEFAULT_MIN_MAGNITUDE = 4.5


class Player:
    """Sends mapped notes to a MIDI sink."""

    def __init__(self, sink) -> None:
        """Create the player.

        Args:
            sink: Anything with ``send(msg)``.
        """
        self._sink = sink

    def play(self, notes: list[mapping.Note]) -> None:
        """Play a gesture of notes, honouring each delay and duration.

        Each note is turned into a note-on at ``delay_ms`` and a note-off at
        ``delay_ms + duration_ms``. The events are sent in time order, and
        the call returns after the last note-off.

        Args:
            notes: Notes from :func:`q2m.mapping.map_event`.
        """
        if not notes:
            return
        events: list[tuple[float, str, mapping.Note]] = []
        for note in notes:
            at = note.delay_ms / 1000.0
            events.append((at, "note_on", note))
            events.append((at + note.duration_ms / 1000.0, "note_off", note))
        events.sort(key=lambda item: (item[0], item[1] == "note_on"))

        started = time.monotonic()
        for at, kind, note in events:
            wait = started + at - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._send(kind, note)

    def _send(self, kind: str, note: mapping.Note) -> None:
        """Send one note-on or note-off message.

        Args:
            kind: ``"note_on"`` or ``"note_off"``.
            note: The note the message is for.
        """
        velocity = note.velocity if kind == "note_on" else 0
        self._sink.send(mido.Message(
            kind,
            note=note.note,
            velocity=velocity,
            channel=note.channel,
        ))


def run_once(
    sink,
    state: State,
    min_magnitude: float,
    seen: set[str],
    dry_run: bool = False,
) -> int:
    """Poll the feed once and play any new events.

    Args:
        sink: The MIDI sink to play through.
        state: The state to record into.
        min_magnitude: The FDSN magnitude floor.
        seen: The set of event ids already played this run.
        dry_run: If True, print notes instead of sounding them.

    Returns:
        How many events were played.
    """
    try:
        events = quakes.fetch_live_earthquakes(min_magnitude)
    except (OSError, ValueError) as err:
        state.error(f"{type(err).__name__}: {err}")
        print(f" [warn] fetch failed: {err}", file=sys.stderr, flush=True)
        return 0

    state.polled()
    played = 0
    player = Player(sink)
    for event in events:
        if event["id"] in seen:
            continue
        seen.add(event["id"])
        notes = mapping.map_event(event)
        if dry_run:
            print(
                f" M{event['mag']:<4} {event['region']} -> "
                f"{len(notes)} note(s)",
                flush=True,
            )
        player.play(notes)
        state.record(event, len(notes))
        played += 1
    return played


def run_forever(
    sink,
    state: State,
    min_magnitude: float,
    interval_s: float = POLL_INTERVAL_S,
) -> None:
    """Poll the feed on an interval until interrupted.

    Args:
        sink: The MIDI sink to play through.
        state: The state to record into.
        min_magnitude: The FDSN magnitude floor.
        interval_s: Seconds between polls.
    """
    seen: set[str] = set()
    print(
        f" watching M{min_magnitude}+ every {interval_s:.0f}s "
        "(Ctrl+C to stop)",
        flush=True,
    )
    while True:
        run_once(sink, state, min_magnitude, seen)
        time.sleep(interval_s)