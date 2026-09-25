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
from q2m.keys import KeyWatcher
from q2m.state import State

POLL_INTERVAL_S = 8.0
# Play everything the feed has. The feed's own floor is about M0.8, so asking
# for 0.0 and asking for 1.0 return the same events; 0.0 simply says "no
# threshold of ours". The steady-state arrival rate is about 16 events an
# hour worldwide.
DEFAULT_MIN_MAGNITUDE = 0.0

# Force the output back to silence if no event has played for this long, so
# nothing can stay sounding. The longest gesture is under 4 s, so 30 s is
# comfortably clear of normal playing.
SILENCE_AFTER_S = 30.0

# The magnitude the spacebar fakes, for testing a patch without waiting for
# the Earth to oblige.
FAKE_MAGNITUDE = 3.2
# A place and depth that map to a mid-range pitch, so the fake event sounds
# like a plausible quake rather than an extreme one.
_FAKE_LAT = 38.7
_FAKE_LON = -9.1
_FAKE_DEPTH_KM = 10.0


def fake_event(magnitude: float = FAKE_MAGNITUDE) -> dict:
    """Return a synthetic event, shaped like one from the feed.

    Args:
        magnitude: The magnitude to fake.

    Returns:
        An event dict with the same keys as
        :func:`q2m.quakes.fetch_live_earthquakes`.
    """
    return {
        "id": f"fake-{time.time_ns()}",
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mag": magnitude,
        "lat": _FAKE_LAT,
        "lon": _FAKE_LON,
        "depth": _FAKE_DEPTH_KM,
        "region": "FAKE (spacebar)",
    }


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
    channel: int | None = mapping.DEFAULT_CHANNEL,
) -> int:
    """Poll the feed once and play any new events.

    Args:
        player: The player to send notes through.
        state: The state to record into.
        min_magnitude: The FDSN magnitude floor.
        seen: The set of event ids already played this run.
        dry_run: If True, print a line per event before playing it.
        lookback_s: How far back the fetch asks, in seconds.
        channel: The MIDI channel to send on, or None to spread events
            across eight channels by longitude and magnitude.

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
        notes = mapping.map_event(event, channel)
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
    skip_existing: bool = False,
    channel: int | None = mapping.DEFAULT_CHANNEL,
    watch_keys: bool = False,
    fake_magnitude: float = FAKE_MAGNITUDE,
    silence_after_s: float = SILENCE_AFTER_S,
) -> None:
    """Poll the feed on an interval until interrupted.

    Args:
        player: The player to send notes through.
        state: The state to record into.
        min_magnitude: The FDSN magnitude floor.
        interval_s: Seconds between polls.
        lookback_s: How far back each fetch asks, in seconds.
        skip_existing: If True, mark the events already in the window as
            seen instead of playing them. The default plays them, so the
            bridge makes sound from the first second rather than waiting
            for the next event to be published.
        channel: The MIDI channel to send on, or None to spread events
            across eight channels by longitude and magnitude.
        watch_keys: If True, listen for the spacebar and play a fake event
            when it is pressed.
        fake_magnitude: The magnitude the spacebar fakes.
        silence_after_s: Force the output back to silence after this many
            seconds with no event. Use 0 to disable.
    """
    if skip_existing:
        seen = prime_seen(state, min_magnitude, lookback_s)
    else:
        seen: set[str] = set()

    watcher = KeyWatcher() if watch_keys else None
    if watcher is not None and not watcher.start():
        print(" [warn] cannot read keys here; spacebar disabled")
        watcher = None

    print(
        f" watching M{min_magnitude}+ every {interval_s:.0f}s "
        "(Ctrl+C to stop)",
        flush=True,
    )

    # Nothing should stay sounding. If no event has played for a while, the
    # output is forced back to silence, so a stuck note cannot hang forever.
    last_sound = time.monotonic()
    silenced = False

    try:
        while True:
            played = run_once(
                player, state, min_magnitude, seen,
                lookback_s=lookback_s, channel=channel,
            )
            if played:
                last_sound = time.monotonic()
                silenced = False

            # Wait out the interval. With a watcher we also wake on a
            # keypress; either way the silence check runs every half second
            # so the output cannot stay sounding.
            deadline = time.monotonic() + interval_s
            while True:
                if not silenced and silence_after_s and \
                        time.monotonic() - last_sound >= silence_after_s:
                    player.panic()
                    silenced = True
                    print(
                        f" silence: nothing for {silence_after_s:.0f}s",
                        flush=True,
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if watcher is None:
                    time.sleep(min(remaining, 0.5))
                    continue
                key = watcher.get(min(remaining, 0.5))
                if key == " ":
                    play_fake(player, state, fake_magnitude, channel)
                    last_sound = time.monotonic()
                    silenced = False
                    break
    finally:
        if watcher is not None:
            watcher.stop()
        player.panic()


def play_fake(
    player: Player,
    state: State,
    magnitude: float = FAKE_MAGNITUDE,
    channel: int | None = mapping.DEFAULT_CHANNEL,
) -> int:
    """Play one synthetic event, as if it had come from the feed.

    Args:
        player: The player to send notes through.
        state: The state to record into.
        magnitude: The magnitude to fake.
        channel: The MIDI channel to send on, or None to spread.

    Returns:
        How many notes were played.
    """
    event = fake_event(magnitude)
    notes = mapping.map_event(event, channel)
    print(
        f" FAKE  M{event['mag']:<4} {event['region']} -> "
        f"{len(notes)} note(s)",
        flush=True,
    )
    player.play(notes)
    state.record(event, len(notes))
    return len(notes)