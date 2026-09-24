"""Map an earthquake to MIDI notes.

The mapping turns the three things an event tells us into music:

- **Magnitude** sets velocity and how long the gesture lasts, and how many
  notes it has. A magnitude 1 is a single soft note; a magnitude 6 is a
  loud five-note run.
- **Latitude** picks the pitch, on a pentatonic scale so any two events
  sound consonant together.
- **Depth** drops the octave: a deep event sounds low, a shallow one high.

Longitude and magnitude together place the event on a MIDI channel, so a DAW
can route different oceans to different instruments if it wants to.
"""

from __future__ import annotations

from dataclasses import dataclass

# A minor pentatonic, two octaves, as semitone offsets from the root.
_SCALE = (0, 3, 5, 7, 10, 12, 15, 17, 19, 22)
_ROOT_NOTE = 48  # C3

# The feed's own floor is about M0.8, so the mapping's floor sits just below
# it. With the floor at 2.0, a fifth of the events clamped to the minimum and
# came out as one barely-audible note.
_MAG_FLOOR = 0.5
_MAG_CEIL = 7.0
_MIN_VELOCITY = 35
_MAX_VELOCITY = 127
_MIN_DURATION_MS = 120
_MAX_DURATION_MS = 900
_MAX_NOTES = 5

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


def map_event(event: dict, channel: int | None = DEFAULT_CHANNEL) -> list[Note]:
    """Map one quake event to the notes it should play.

    Args:
        event: An event dict from :func:`q2m.quakes.fetch_live_earthquakes`.
        channel: The MIDI channel to send on, 0-15. Pass None to spread
            events across eight channels by longitude and magnitude.

    Returns:
        One to five notes, in the order they should be sent.
    """
    mag = float(event["mag"])
    unit = _unit(mag)
    spread = _MAX_VELOCITY - _MIN_VELOCITY
    velocity = int(round(_MIN_VELOCITY + unit * spread))
    duration = int(round(
        _MIN_DURATION_MS + unit * (_MAX_DURATION_MS - _MIN_DURATION_MS)
    ))
    count = 1 + int(round(unit * (_MAX_NOTES - 1)))
    if channel is None:
        channel = _channel(float(event["lon"]), mag)
    shift = _octave_shift(event.get("depth"))
    base = _ROOT_NOTE + _SCALE[_pitch_index(float(event["lat"]))] + shift

    step = max(30, duration // (count + 1))
    notes = []
    for i in range(count):
        pitch = _clamp(base + i * 2, 0, 127)
        notes.append(Note(
            note=int(pitch),
            velocity=velocity,
            channel=channel,
            delay_ms=i * step,
            duration_ms=duration,
        ))
    return notes