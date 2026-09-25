"""Tests for the spacebar fake event and the key watcher."""

from __future__ import annotations

import tempfile
from pathlib import Path

from q2m import core, keys, mapping
from q2m.state import State


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


def a_state() -> State:
    """Return a State writing into a temporary directory."""
    return State(Path(tempfile.mkdtemp()))


def test_fake_event_has_the_feed_shape():
    event = core.fake_event()
    for key in ("id", "time", "mag", "lat", "lon", "depth", "region"):
        assert key in event, key


def test_fake_event_defaults_to_m5():
    assert core.fake_event()["mag"] == 5.0


def test_fake_event_magnitude_is_settable():
    assert core.fake_event(7.2)["mag"] == 7.2


def test_fake_event_ids_are_unique():
    # Two presses in the same second must not collide, or the second would
    # be deduped away.
    ids = {core.fake_event()["id"] for _ in range(50)}
    assert len(ids) == 50


def test_fake_event_maps_to_notes():
    notes = mapping.map_event(core.fake_event())
    assert notes
    assert all(0 <= n.note <= 127 for n in notes)


def test_fake_event_is_louder_than_a_small_real_one():
    fake = mapping.map_event(core.fake_event())[0]
    small = mapping.map_event(core.fake_event(1.0))[0]
    assert fake.velocity > small.velocity


def test_play_fake_sends_notes_and_records():
    sink = RecordingSink()
    st = a_state()
    count = core.play_fake(core.Player(sink), st, 5.0)
    assert count > 0
    assert sink.types.count("note_on") == count
    assert sink.types.count("note_off") == count
    snapshot = st.snapshot()
    assert snapshot["events_total"] == 1
    assert snapshot["recent"][0]["region"] == "FAKE (spacebar)"


def test_play_fake_releases_every_note():
    sink = RecordingSink()
    core.play_fake(core.Player(sink), a_state(), 5.0)
    assert sink.types.count("note_on") == sink.types.count("note_off")


def test_key_watcher_reports_support():
    # On any platform we run on, one of the two backends exists.
    assert isinstance(keys.KeyWatcher.supported(), bool)


def test_key_watcher_get_times_out_without_keys():
    watcher = keys.KeyWatcher()
    assert watcher.get(0.05) is None


def test_key_watcher_stop_is_safe_without_start():
    watcher = keys.KeyWatcher()
    watcher.stop()
    watcher.restore()


def test_key_watcher_start_returns_false_when_not_a_tty(monkeypatch):
    # Under pytest stdin is not a terminal, so the watcher must decline
    # rather than break the terminal.
    watcher = keys.KeyWatcher()
    monkeypatch.setattr(keys.sys.stdin, "isatty", lambda: False)
    assert watcher.start() is False


def test_restore_is_idempotent():
    watcher = keys.KeyWatcher()
    watcher.restore()
    watcher.restore()
    assert watcher._saved is None


def test_stop_removes_signal_guards():
    watcher = keys.KeyWatcher()
    watcher.stop()
    assert watcher._prev_handlers == {}


def test_fatal_signals_are_guarded_on_posix():
    # SIGTERM and SIGHUP kill the process without running `finally`, which
    # would leave the shell with no echo. They must be handled.
    if keys.termios is None:
        return
    assert "SIGTERM" in keys._FATAL_SIGNALS
    assert "SIGHUP" in keys._FATAL_SIGNALS
    # SIGINT is deliberately absent: it raises KeyboardInterrupt instead.
    assert "SIGINT" not in keys._FATAL_SIGNALS
