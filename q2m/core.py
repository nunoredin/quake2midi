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

from q2m import mapping, midi, quakes
from q2m.state import State

POLL_INTERVAL_S = 8.0
DEFAULT_MIN_MAGNITUDE = 4.5


class Player:
    """Sends mapped notes to a MIDI sink.

    The player keeps track of the notes it has turned on but not yet off, so
    that :meth:`panic` can release exactly those and then silence the port.
    """

    def __init__(self, sink) -> None:
        """Create the player.

        Args:
            sink: Anything with ``send(msg)``.
        """
        self._sink = sink
        self._active: set[tuple[int, int]] = set()

    def play(self, notes: list[mapping.Note]) -> None:
        """Play a gesture of notes, honouring each delay and duration.

        Each note is turned into a note-on at ``delay_ms`` and a note-off at
        ``delay_ms + duration_ms``. The events are sent in time order, and
        the call returns after the last note-off. An interrupt releases the
        notes that are still sounding, then propagates.

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
        events.sort(key=lambda item: (item[0], item[1] != "note_on"))

        try:
            started = time.monotonic()
            for at, kind, note in events:
                wait = started + at - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._send(kind, note)
        except KeyboardInterrupt:
            self.panic()
            raise

    def panic(self) -> None:
        """Release the sounding notes, then silence every channel."""
        for note, channel in sorted(self._active):
            self._sink.send(mido.Message(
                "note_off",
                note=note,
                velocity=0,
                channel=channel,
            ))
        self._active.clear()
        midi.all_notes_off(self._sink)

    def _send(self, kind: str, note: mapping.Note) -> None:
        """Send one note-on or note-off message, tracking active notes.

        Args:
            kind: ``"note_on"`` or ``"note_off"``.
            note: The note the message is for.
        """
        key = (note.note, note.channel)
        if kind == "note_on":
            self._active.add(key)
        else:
            self._active.discard(key)
        velocity = note.velocity if kind == "note_on" else 0
        self._sink.send(mido.Message(
            kind,
            note=note.note,
            velocity=velocity,
            channel=note.channel,
        ))


def prime_seen(
    state: State,
    min_magnitude: float,
    lookback_s: int,
) -> set[str]:
    """Fetch once and return the ids to treat as already played.

    The lookback window is wider than the poll interval, so the first fetch
    of a run can return an hour of history. Playing all of it at start-up
    would be a burst of unrelated events, so the loop primes the seen set
    with whatever is there and plays only what arrives afterwards.

    Args:
        state: The state to record the priming poll into.
        min_magnitude: The FDSN magnitude floor.
        lookback_s: How far back the fetch asks, in seconds.

    Returns:
        The ids present at start-up. Empty if the fetch fails.
    """
    try:
        events = quakes.fetch_live_earthquakes(min_magnitude, lookback_s)
    except (OSError, ValueError) as err:
        state.error(f"{type(err).__name__}: {err}")
        print(f" [warn] priming fetch failed: {err}", file=sys.stderr,
              flush=True)
        return set()
    state.polled()
    if events:
        print(f" priming: {len(events)} existing event(s) marked as seen",
              flush=True)
    return {event["id"] for event in events}


def run_once(
    player: Player,
    state: State,
    min_magnitude: float,
    seen: set[str],
    dry_run: bool = False,
    lookback_s: int = quakes.EQ_LOOKBACK_S,
) -> int:
    """Poll the feed once and play any new events.

    Args:
        player: The player to send notes through.
        state: The state to record into.
        min_magnitude: The FDSN magnitude floor.
        seen: The set of event ids already played this run.
        dry_run: If True, print a line per event before playing it.
        lookback_s: How far back the fetch asks, in seconds.

    Returns:
        How many events were played.
    """
    try:
        events = quakes.fetch_live_earthquakes(min_magnitude, lookback_s)
    except (OSError, ValueError) as err:
        state.error(f"{type(err).__name__}: {err}")
        print(f" [warn] fetch failed: {err}", file=sys.stderr, flush=True)
        return 0

    state.polled()
    played = 0
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
    player: Player,
    state: State,
    min_magnitude: float,
    interval_s: float = POLL_INTERVAL_S,
    lookback_s: int = quakes.EQ_LOOKBACK_S,
    play_existing: bool = False,
) -> None:
    """Poll the feed on an interval until interrupted.

    Args:
        player: The player to send notes through.
        state: The state to record into.
        min_magnitude: The FDSN magnitude floor.
        interval_s: Seconds between polls.
        lookback_s: How far back each fetch asks, in seconds.
        play_existing: If True, play the events already in the window at
            start-up instead of marking them as seen.
    """
    if play_existing:
        seen: set[str] = set()
    else:
        seen = prime_seen(state, min_magnitude, lookback_s)
    print(
        f" watching M{min_magnitude}+ every {interval_s:.0f}s "
        "(Ctrl+C to stop)",
        flush=True,
    )
    try:
        while True:
            run_once(
                player, state, min_magnitude, seen,
                lookback_s=lookback_s,
            )
            time.sleep(interval_s)
    finally:
        player.panic()