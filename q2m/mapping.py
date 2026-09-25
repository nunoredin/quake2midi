"""Map an earthquake to MIDI notes.

The mapping reads the magnitude as a regime, and the three regimes are
meant to be told apart by ear:

- **Small** (below M3) is a *tiny flash*: one note, very short, quiet.
- **Medium** (M3 to M5) is *unstable*: several notes that jump around,
  with uneven timing and uneven dynamics, so it never settles into a
  pattern.
- **Hard** (M5 and up) is *long and strong*: many loud notes, each held
  for a long time, overlapping into a sustained gesture.

The velocity and duration ranges of the three regimes do not overlap, so a
harder quake is always louder and longer than a weaker one, not just
differently shaped.

- **Latitude** picks the pitch, on a pentatonic scale so any two events
  sound consonant together.
- **Depth** drops the octave: a deep event sounds low, a shallow one high.

The medium and hard gestures are generated with a random number generator
seeded from the event id, so a given event always sounds the same way while
different events differ.
"""

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass

# A minor pentatonic, two octaves, as semitone offsets from the root.
_SCALE = (0, 3, 5, 7, 10, 12, 15, 17, 19, 22)
_ROOT_NOTE = 48  # C3

# The feed's own floor is about M0.8, so the mapping's floor sits just below
# it. With the floor at 2.0, a fifth of the events clamped to the minimum and
# came out as one barely-audible note.
_MAG_FLOOR = 0.5
_MAG_CEIL = 7.0

# Regime boundaries, chosen from the feed's own mix over 24 hours: M0-2 23%,
# M2-3 39%, M3-4 28%, M4-5 9%, M5+ 1%. So "small" is the bulk, "medium" a
# third, and "hard" rare enough to be worth the drama.
_SMALL_BELOW = 3.0
_HARD_AT = 5.0

# Small: a tiny flash. One note, barely there.
_SMALL_VELOCITY = (30, 70)
_SMALL_DURATION_MS = (40, 110)
_SMALL_JITTER = 6

# Medium: unstable. Several notes that jump around, unevenly timed and
# unevenly loud, so no two gestures have the same shape.
_MEDIUM_NOTES = (3, 7)
_MEDIUM_VELOCITY = (75, 110)
_MEDIUM_DURATION_MS = (150, 400)
_MEDIUM_JITTER = 6
_MEDIUM_STEP_MS = (0, 90)
# Interval jumps, in semitones. Wide and irregular on purpose.
_MEDIUM_LEAPS = (-12, -7, -5, -2, 0, 3, 5, 7, 12)

# Hard: long and strong. Many loud notes, each held, overlapping.
_HARD_NOTES = (6, 12)
_HARD_VELOCITY = (112, 127)
_HARD_DURATION_MS = (500, 2000)
_HARD_JITTER = 3
_HARD_STEP_MS = (70, 220)
_HARD_LEAPS = (-12, -5, 0, 2, 4, 5, 7, 12)

_DEPTH_SHALLOW_KM = 10.0
_DEPTH_DEEP_KM = 600.0

_CHANNELS = 8
# A synth patch (a VCV Rack MIDI-to-CV, a DAW track) usually listens on one
# channel. Spreading events across eight of them means most notes land
# somewhere nothing is listening, so the default is a single channel.
DEFAULT_CHANNEL = 0


@dataclass(frozen=True)
class Note:
    """One MIDI note in a gesture.

    Attributes:
        note: MIDI note number, 0-127.
        velocity: MIDI velocity, 1-127.
        channel: MIDI channel, 0-15.
        delay_ms: Milliseconds after the gesture starts to send it.
        duration_ms: Milliseconds the note is held.
    """

    note: int
    velocity: int
    channel: int
    delay_ms: int
    duration_ms: int


def _clamp(value: float, low: float, high: float) -> float:
    """Return ``value`` limited to ``[low, high]``."""
    return max(low, min(high, value))


def _unit(mag: float) -> float:
    """Return the magnitude as 0..1 across the useful range."""
    span = _MAG_CEIL - _MAG_FLOOR
    return _clamp((mag - _MAG_FLOOR) / span, 0.0, 1.0)


def _within(mag: float, low: float, high: float) -> float:
    """Return where ``mag`` sits in ``[low, high]``, as 0..1."""
    if high <= low:
        return 0.0
    return _clamp((mag - low) / (high - low), 0.0, 1.0)


def _scaled(
    bounds: tuple[int, int],
    t: float,
    rng: random.Random | None = None,
    jitter: int = 0,
) -> int:
    """Return a value across ``bounds`` by ``t``, with optional jitter.

    The result is clamped to ``bounds``, so jitter can never push a value
    out of its regime and break the ordering between regimes.

    Args:
        bounds: The low and high ends.
        t: Where to land, 0..1.
        rng: Source of jitter, or None for no randomness.
        jitter: Maximum +/- wobble.

    Returns:
        The value, as an int.
    """
    low, high = bounds
    value = low + t * (high - low)
    if rng is not None and jitter:
        value += rng.randint(-jitter, jitter)
    return int(round(_clamp(value, low, high)))


def _seed(event: dict) -> int:
    """Return a stable seed for an event, so a replay sounds the same.

    ``hash()`` is salted per process, so it cannot be used here; crc32 of
    the id is stable across runs.

    Args:
        event: The event dict.

    Returns:
        An int seed.
    """
    return zlib.crc32(str(event.get("id", "")).encode("utf-8"))


def _pitch_index(lat: float) -> int:
    """Return a scale index from a latitude in degrees."""
    frac = _clamp((lat + 90.0) / 180.0, 0.0, 1.0)
    return int(round(frac * (len(_SCALE) - 1)))


def _octave_shift(depth_km: float | None) -> int:
    """Return -12, 0, or +12 semitones from the event depth."""
    if depth_km is None:
        return 0
    span = _DEPTH_DEEP_KM - _DEPTH_SHALLOW_KM
    frac = _clamp((depth_km - _DEPTH_SHALLOW_KM) / span, 0.0, 1.0)
    return int(round((0.5 - frac) * 24 / 12) * 12)


def _channel(lon: float, mag: float) -> int:
    """Return a channel from longitude, offset a little by magnitude."""
    frac = _clamp((lon + 180.0) / 360.0, 0.0, 1.0)
    idx = int(frac * _CHANNELS)
    return (idx + int(_unit(mag) * 2)) % _CHANNELS


def _small(
    mag: float, base: int, channel: int, rng: random.Random,
) -> list[Note]:
    """Return a tiny flash: one short, quiet note.

    Args:
        mag: The event magnitude.
        base: The base pitch.
        channel: The MIDI channel.
        rng: Seeded random source.

    Returns:
        A single note.
    """
    t = _within(mag, _MAG_FLOOR, _SMALL_BELOW)
    return [Note(
        note=int(_clamp(base, 0, 127)),
        velocity=_scaled(_SMALL_VELOCITY, t, rng, _SMALL_JITTER),
        channel=channel,
        delay_ms=0,
        duration_ms=_scaled(_SMALL_DURATION_MS, t, rng, _SMALL_JITTER),
    )]


def _medium(
    mag: float, base: int, channel: int, rng: random.Random,
) -> list[Note]:
    """Return an unstable gesture: uneven timing, jumping pitch.

    Args:
        mag: The event magnitude.
        base: The base pitch.
        channel: The MIDI channel.
        rng: Seeded random source.

    Returns:
        Three to seven notes, in the order they should be sent.
    """
    t = _within(mag, _SMALL_BELOW, _HARD_AT)
    count = rng.randint(*_MEDIUM_NOTES)
    notes = []
    at = 0
    for _ in range(count):
        notes.append(Note(
            note=int(_clamp(base + rng.choice(_MEDIUM_LEAPS), 0, 127)),
            velocity=_scaled(_MEDIUM_VELOCITY, t, rng, _MEDIUM_JITTER),
            channel=channel,
            delay_ms=at,
            duration_ms=_scaled(_MEDIUM_DURATION_MS, t, rng, _MEDIUM_JITTER),
        ))
        at += rng.randint(*_MEDIUM_STEP_MS)
    return notes


def _hard(
    mag: float, base: int, channel: int, rng: random.Random,
) -> list[Note]:
    """Return a long, strong gesture: many loud notes, each held.

    Args:
        mag: The event magnitude.
        base: The base pitch.
        channel: The MIDI channel.
        rng: Seeded random source.

    Returns:
        Six to twelve notes, in the order they should be sent.
    """
    t = _within(mag, _HARD_AT, _MAG_CEIL)
    count = rng.randint(*_HARD_NOTES)
    notes = []
    at = 0
    for _ in range(count):
        notes.append(Note(
            note=int(_clamp(base + rng.choice(_HARD_LEAPS), 0, 127)),
            velocity=_scaled(_HARD_VELOCITY, t, rng, _HARD_JITTER),
            channel=channel,
            delay_ms=at,
            duration_ms=_scaled(_HARD_DURATION_MS, t, rng, _HARD_JITTER),
        ))
        at += rng.randint(*_HARD_STEP_MS)
    return notes


def map_event(event: dict, channel: int | None = DEFAULT_CHANNEL) -> list[Note]:
    """Map one quake event to the notes it should play.

    Args:
        event: An event dict from :func:`q2m.quakes.fetch_live_earthquakes`.
        channel: The MIDI channel to send on, 0-15. Pass None to spread
            events across eight channels by longitude and magnitude.

    Returns:
        The notes of the gesture, in the order they should be sent.
    """
    mag = float(event["mag"])
    if channel is None:
        channel = _channel(float(event["lon"]), mag)
    shift = _octave_shift(event.get("depth"))
    base = _ROOT_NOTE + _SCALE[_pitch_index(float(event["lat"]))] + shift
    rng = random.Random(_seed(event))

    if mag < _SMALL_BELOW:
        return _small(mag, base, channel, rng)
    if mag < _HARD_AT:
        return _medium(mag, base, channel, rng)
    return _hard(mag, base, channel, rng)