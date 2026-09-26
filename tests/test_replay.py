"""Tests for the paced start-up replay.

The first fetch of a run can return hours of history. ``ReplayQueue``
spreads that backlog across a fixed window, oldest first, so the piece
opens gently instead of as a burst. Live events never go through the
queue, so they jump ahead of it.

These tests drive the loop with a stubbed clock and a stubbed feed, so
they run instantly and touch no network.
"""

from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from q2m import core
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


def an_event(n: int, region: str = "TEST") -> dict:
    """Return a distinct fake feed event, ordered by ``n``."""
    return {
        "id": f"e{n}", "time": f"2026-01-01T00:00:{n:02d}Z", "mag": 4.0,
        "lat": 0.0, "lon": 0.0, "depth": None, "region": region,
    }


# --- ReplayQueue, on its own -------------------------------------------


def test_queue_orders_oldest_first():
    events = [an_event(3), an_event(1), an_event(2)]
    queue = core.ReplayQueue(events, 120.0, start=0.0)
    assert [e["id"] for e in queue.due(1000.0)] == ["e1", "e2", "e3"]


def test_queue_first_event_is_due_immediately():
    queue = core.ReplayQueue([an_event(1), an_event(2)], 120.0, start=0.0)
    assert [e["id"] for e in queue.due(0.0)] == ["e1"]


def test_queue_spaces_events_evenly():
    events = [an_event(i) for i in range(1, 5)]
    queue = core.ReplayQueue(events, 120.0, start=0.0)
    # Four events over 120 s is one every 30 s.
    assert queue.due(0.0) == [events[0]]
    assert queue.due(29.9) == []
    assert [e["id"] for e in queue.due(30.0)] == ["e2"]
    assert [e["id"] for e in queue.due(90.0)] == ["e3", "e4"]


def test_queue_pending_counts_down():
    queue = core.ReplayQueue([an_event(1), an_event(2)], 120.0, start=0.0)
    assert queue.pending == 2
    queue.due(0.0)
    assert queue.pending == 1
    queue.due(1000.0)
    assert queue.pending == 0


def test_queue_is_empty_without_events():
    queue = core.ReplayQueue([], 120.0, start=0.0)
    assert queue.pending == 0
    assert queue.due(0.0) == []


def test_queue_never_replays_an_event():
    queue = core.ReplayQueue([an_event(1)], 120.0, start=0.0)
    assert len(queue.due(0.0)) == 1
    assert queue.due(1000.0) == []


# --- run_forever, with the queue wired in ------------------------------


def drive_replay(
    monkeypatch,
    polls: int,
    replay_window: float,
    backlog: list[dict],
    live_per_poll: int = 0,
    silence_after: float = 10.0,
    interval: float = 8.0,
) -> tuple[RecordingSink, State, str]:
    """Run the loop with a backlog, then stop.

    The first fetch returns ``backlog``; every later fetch returns
    ``live_per_poll`` fresh events.

    Args:
        monkeypatch: pytest fixture.
        polls: How many ``run_once`` polls to run before stopping.
        replay_window: The replay window to pass in.
        backlog: The events the first fetch returns.
        live_per_poll: How many fresh events each later poll returns.
        silence_after: The watchdog delay to pass in.
        interval: Seconds between polls.

    Returns:
        The sink, the state, and the captured stdout.
    """
    clock = FakeTime()
    monkeypatch.setattr(core, "time", clock)

    calls = {"n": 0}

    def fake_fetch(mag: float, lookback: int) -> list[dict]:
        del mag, lookback
        calls["n"] += 1
        if calls["n"] == 1:
            return list(backlog)
        start = (calls["n"] - 2) * live_per_poll
        return [
            an_event(1000 + i, region="LIVE")
            for i in range(start, start + live_per_poll)
        ]

    monkeypatch.setattr(core.quakes, "fetch_live_earthquakes", fake_fetch)

    sink = RecordingSink()
    st = a_state()
    seen_polls = {"n": 0}
    real_run_once = core.run_once

    def counting_run_once(*args, **kwargs):
        seen_polls["n"] += 1
        if seen_polls["n"] > polls:
            raise StopLoop
        return real_run_once(*args, **kwargs)

    monkeypatch.setattr(core, "run_once", counting_run_once)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        with pytest.raises(StopLoop):
            core.run_forever(
                core.Player(sink), st, 0.0,
                interval_s=interval, lookback_s=3600,
                silence_after_s=silence_after,
                replay_window_s=replay_window,
            )
    return sink, st, buffer.getvalue()


def test_replay_spreads_the_backlog(monkeypatch):
    # Four events over 120 s is one every 30 s. Two polls is 16 s, so only
    # the first event has played.
    backlog = [an_event(i) for i in range(1, 5)]
    _, st, out = drive_replay(
        monkeypatch, polls=1, replay_window=120.0, backlog=backlog,
    )
    assert st.snapshot()["events_total"] == 1
    assert "replay: 4 event(s) over 120s" in out


def test_replay_window_zero_plays_the_backlog_at_once(monkeypatch):
    backlog = [an_event(i) for i in range(1, 5)]
    _, st, out = drive_replay(
        monkeypatch, polls=1, replay_window=0.0, backlog=backlog,
    )
    assert st.snapshot()["events_total"] == 4
    assert "replay:" not in out


def test_replay_suppresses_the_watchdog_while_draining(monkeypatch):
    # Ten events over 120 s is one every 12 s, and the watchdog is 10 s.
    # Without suppression each gap would silence the port; with it, the
    # only silence comes after the backlog has drained.
    backlog = [an_event(i) for i in range(1, 11)]
    _, st, out = drive_replay(
        monkeypatch, polls=20, replay_window=120.0, backlog=backlog,
        silence_after=10.0,
    )
    assert st.snapshot()["events_total"] == 10
    assert out.count("silence") == 1


def test_live_events_jump_the_replay_queue(monkeypatch):
    # The backlog is still draining when a live event arrives; it must
    # play at once rather than wait its turn.
    backlog = [an_event(i) for i in range(1, 5)]
    _, st, _ = drive_replay(
        monkeypatch, polls=1, replay_window=120.0, backlog=backlog,
        live_per_poll=1,
    )
    regions = [item["region"] for item in st.snapshot()["recent"]]
    assert "LIVE" in regions
    assert st.snapshot()["events_total"] == 2


def test_skip_existing_ignores_the_replay_window(monkeypatch):
    backlog = [an_event(i) for i in range(1, 5)]
    clock = FakeTime()
    monkeypatch.setattr(core, "time", clock)
    monkeypatch.setattr(
        core.quakes, "fetch_live_earthquakes",
        lambda mag, lookback: list(backlog),
    )
    sink = RecordingSink()
    st = a_state()
    seen_polls = {"n": 0}
    real_run_once = core.run_once

    def counting_run_once(*args, **kwargs):
        seen_polls["n"] += 1
        if seen_polls["n"] > 1:
            raise StopLoop
        return real_run_once(*args, **kwargs)

    monkeypatch.setattr(core, "run_once", counting_run_once)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        with pytest.raises(StopLoop):
            core.run_forever(
                core.Player(sink), st, 0.0,
                interval_s=8.0, lookback_s=3600,
                skip_existing=True, replay_window_s=120.0,
            )
    # The backlog was primed as seen, so nothing was replayed.
    assert st.snapshot()["events_total"] == 0
    assert "replay:" not in buffer.getvalue()


def test_replay_default_window_is_two_minutes():
    assert core.REPLAY_WINDOW_S == 120.0
