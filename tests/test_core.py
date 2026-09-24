"""Tests for :class:`q2m.core.Player` and the run loop helpers."""

from __future__ import annotations

import pytest

from q2m import core, mapping, midi


class RecordingSink:
    """A sink that records every message it is sent."""

    def __init__(self) -> None:
        """Create an empty sink."""
        self.messages: list = []

    def send(self, msg) -> None:
        """Record one message."""
        self.messages.append(msg)

    def close(self) -> None:
        """Do nothing."""

    @property
    def types(self) -> list[str]:
        """Return the recorded message types, in order."""
        return [m.type for m in self.messages]


def a_note(**overrides: object) -> mapping.Note:
    """Return one note, with ``overrides`` applied."""
    base = {
        "note": 60,
        "velocity": 100,
        "channel": 0,
        "delay_ms": 0,
        "duration_ms": 0,
    }
    base.update(overrides)
    return mapping.Note(**base)


def test_play_sends_on_then_off():
    sink = RecordingSink()
    core.Player(sink).play([a_note()])
    assert sink.types == ["note_on", "note_off"]


def test_play_off_carries_zero_velocity():
    sink = RecordingSink()
    core.Player(sink).play([a_note(velocity=99)])
    assert sink.messages[0].velocity == 99
    assert sink.messages[1].velocity == 0


def test_play_does_nothing_without_notes():
    sink = RecordingSink()
    core.Player(sink).play([])
    assert sink.messages == []


def test_play_orders_note_on_before_note_off():
    sink = RecordingSink()
    notes = [
        a_note(note=60, delay_ms=0, duration_ms=100),
        a_note(note=62, delay_ms=50, duration_ms=100),
    ]
    core.Player(sink).play(notes)
    # The second note starts before the first one ends.
    assert sink.types == [
        "note_on", "note_on", "note_off", "note_off",
    ]


def test_panic_releases_active_notes_then_silences():
    sink = RecordingSink()
    player = core.Player(sink)
    player._active.add((60, 0))
    player.panic()
    # One explicit note-off for the tracked note...
    assert sink.messages[0].type == "note_off"
    assert sink.messages[0].note == 60
    # ...then All Sound Off and All Notes Off on all 16 channels.
    controls = [m.control for m in sink.messages if m.type == "control_change"]
    assert len(controls) == 32
    assert set(controls) == {120, 123}
    assert player._active == set()


def test_panic_is_safe_when_nothing_is_active():
    sink = RecordingSink()
    core.Player(sink).panic()
    assert all(m.type == "control_change" for m in sink.messages)


def test_play_interrupt_releases_notes_and_reraises(monkeypatch):
    sink = RecordingSink()
    player = core.Player(sink)
    notes = [a_note(delay_ms=0, duration_ms=10_000)]

    def fake_sleep(seconds: float) -> None:
        del seconds
        # The note-on is already out; interrupt before the note-off.
        raise KeyboardInterrupt

    monkeypatch.setattr(core.time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        player.play(notes)

    # The note was turned on, then released by the panic.
    assert sink.types[0] == "note_on"
    assert "note_off" in sink.types
    assert player._active == set()


def test_all_notes_off_tolerates_rejecting_channels():
    class PickySink:
        def __init__(self) -> None:
            self.sent = 0

        def send(self, msg) -> None:
            self.sent += 1
            if msg.channel != 0:
                raise ValueError("channel not supported")

    sink = PickySink()
    midi.all_notes_off(sink)
    # Two controls on channel 0 only; the other 30 raised and were skipped.
    assert sink.sent == 32


def fake_state():
    """Return a State writing into a temporary directory."""
    import tempfile
    from pathlib import Path

    from q2m.state import State

    return State(Path(tempfile.mkdtemp()))


def test_prime_seen_returns_existing_ids(monkeypatch):
    events = [{"id": "a", "mag": 4.0}, {"id": "b", "mag": 5.0}]
    monkeypatch.setattr(
        core.quakes, "fetch_live_earthquakes",
        lambda mag, lookback_s: events,
    )
    assert core.prime_seen(fake_state(), 4.0, 3600) == {"a", "b"}


def test_prime_seen_is_empty_when_the_fetch_fails(monkeypatch):
    def boom(mag, lookback_s):
        raise OSError("no network")

    monkeypatch.setattr(core.quakes, "fetch_live_earthquakes", boom)
    assert core.prime_seen(fake_state(), 4.0, 3600) == set()


def test_run_once_skips_seen_and_plays_new(monkeypatch):
    events = [
        {"id": "old", "mag": 4.0, "lat": 0.0, "lon": 0.0, "depth": None,
         "region": "OLD", "time": "t"},
        {"id": "new", "mag": 5.0, "lat": 0.0, "lon": 0.0, "depth": None,
         "region": "NEW", "time": "t"},
    ]
    monkeypatch.setattr(
        core.quakes, "fetch_live_earthquakes",
        lambda mag, lookback_s: events,
    )
    sink = RecordingSink()
    seen = {"old"}
    played = core.run_once(
        core.Player(sink), fake_state(), 4.0, seen, dry_run=True,
    )
    assert played == 1
    assert seen == {"old", "new"}
    # Only the new event sounded, and its notes were released.
    assert sink.types.count("note_on") == sink.types.count("note_off")


def test_run_once_records_a_fetch_failure(monkeypatch):
    def boom(mag, lookback_s):
        raise OSError("no network")

    monkeypatch.setattr(core.quakes, "fetch_live_earthquakes", boom)
    st = fake_state()
    assert core.run_once(core.Player(RecordingSink()), st, 4.0, set()) == 0
    assert "OSError" in (st.snapshot().get("last_error") or "")