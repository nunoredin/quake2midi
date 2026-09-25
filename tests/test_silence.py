"""Tests for the silence watchdog and the terminal output.

The watchdog forces the output back to silence after a quiet spell, so a
stuck note cannot hang forever. These tests drive the loop with a stubbed
clock and a stubbed feed, so they run instantly and touch no network.

``run_forever`` always ends with ``player.panic()``, so one all-notes-off
batch is expected even when the watchdog never fires. A panic is 32 control
messages (two per channel, across 16 channels), so the tests count panics.
"""

from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from q2m import core, mapping
from q2m.state import State

_CONTROLS_PER_PANIC = 32


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
    def panics(self) -> int:
        """Return how many all-notes-off batches were sent.

        A panic starts with All Sound Off on channel 0, so counting those
        markers counts the panics.
        """
        return sum(
            1 for m in self.messages
            if m.type == "control_change" and m.control == 120
            and m.channel == 0
        )

    @property
    def controls(self) -> int:
        """Return how many control_change messages were sent."""
        return sum(1 for m in self.messages if m.type == "control_change")


class FakeTime:
    """A stand-in for the ``time`` module that only moves when told to."""

    def __init__(self) -> None:
        """Start at zero."""
        self.now = 0.0

    def monotonic(self) -> float:
        """Return the current time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Move the clock forward."""
        self.now += seconds

    def strftime(self, fmt: str, *args: object) -> str:
        """Return a placeholder timestamp."""
        del fmt, args
        return "2026-01-01T00:00:00Z"

    def gmtime(self, *args: object) -> object:
        """Return a placeholder time tuple."""
        del args
        return None

    def time_ns(self) -> int:
        """Return the clock in nanoseconds."""
        return int(self.now * 1e9)


def a_state() -> State:
    """Return a State writing into a temporary directory."""
    return State(Path(tempfile.mkdtemp()))


class StopLoop(Exception):
    """Raised to break out of run_forever in a test."""


def an_event(n: int) -> dict:
    """Return a distinct fake feed event."""
    return {
        "id": f"e{n}", "time": "t", "mag": 4.0, "lat": 0.0, "lon": 0.0,
        "depth": None, "region": "TEST",
    }


def drive(
    monkeypatch,
    polls: int,
    silence_after: float,
    events_per_poll: int = 0,
) -> tuple[RecordingSink, str]:
    """Run the loop for a fixed number of polls, then stop.

    Args:
        monkeypatch: pytest fixture.
        polls: How many polls to run before stopping.
        silence_after: The watchdog delay to pass in.
        events_per_poll: How many fresh events each poll returns.

    Returns:
        The sink and the captured stdout.
    """
    clock = FakeTime()
    monkeypatch.setattr(core, "time", clock)

    counter = {"n": 0}

    def fake_fetch(mag: float, lookback: int) -> list[dict]:
        del mag, lookback
        start = counter["n"] * events_per_poll
        return [an_event(i) for i in range(start, start + events_per_poll)]

    monkeypatch.setattr(core.quakes, "fetch_live_earthquakes", fake_fetch)

    sink = RecordingSink()
    seen_polls = {"n": 0}
    real_run_once = core.run_once

    def counting_run_once(*args, **kwargs):
        seen_polls["n"] += 1
        if seen_polls["n"] > polls:
            raise StopLoop
        counter["n"] = seen_polls["n"] - 1
        return real_run_once(*args, **kwargs)

    monkeypatch.setattr(core, "run_once", counting_run_once)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        with pytest.raises(StopLoop):
            core.run_forever(
                core.Player(sink), a_state(), 0.0,
                interval_s=8.0, lookback_s=3600,
                silence_after_s=silence_after,
            )
    return sink, buffer.getvalue()


def test_silence_constant_is_clear_of_the_longest_gesture():
    # The longest gesture is under 4 s, so the watchdog must not fire during
    # normal playing.
    assert core.SILENCE_AFTER_S >= 10.0


def test_silence_after_defaults_to_30s():
    assert core.SILENCE_AFTER_S == 30.0


def test_watchdog_silences_the_port_after_a_quiet_spell(monkeypatch):
    # Five polls at 8 s each is 40 s of quiet, past the 30 s watchdog, so
    # there are two panics: the watchdog's, then the one on exit.
    sink, out = drive(monkeypatch, polls=5, silence_after=30.0)
    assert sink.panics == 2
    assert "silence" in out


def test_watchdog_does_not_fire_during_short_quiet_spells(monkeypatch):
    # Two polls is 16 s, short of the 30 s watchdog: only the exit panic.
    sink, out = drive(monkeypatch, polls=2, silence_after=30.0)
    assert sink.panics == 1
    assert "silence" not in out


def test_watchdog_zero_disables_the_silence(monkeypatch):
    sink, out = drive(monkeypatch, polls=5, silence_after=0.0)
    assert sink.panics == 1
    assert "silence" not in out


def test_silence_is_reported_once_per_quiet_spell(monkeypatch):
    sink, out = drive(monkeypatch, polls=8, silence_after=10.0)
    assert out.count("silence") == 1
    assert sink.panics == 2


def test_playing_events_keeps_the_watchdog_quiet(monkeypatch):
    # A fresh event every poll means sound keeps arriving, so only the
    # panic on exit is sent.
    sink, out = drive(
        monkeypatch, polls=8, silence_after=10.0, events_per_poll=1,
    )
    assert sink.panics == 1
    assert "silence" not in out


def test_spacebar_hint_is_not_printed(monkeypatch):
    # The hint was removed: the loop must not mention SPACE.
    _, out = drive(monkeypatch, polls=1, silence_after=30.0)
    assert "SPACE" not in out
    assert "space" not in out.lower()


def test_panic_still_covers_every_channel():
    # The watchdog relies on the existing panic; it must still silence all
    # 16 channels.
    sink = RecordingSink()
    core.Player(sink).panic()
    assert sink.controls == _CONTROLS_PER_PANIC
    assert sink.panics == 1


def test_fake_event_still_maps():
    # The spacebar path is untouched by the watchdog work.
    assert mapping.map_event(core.fake_event())
