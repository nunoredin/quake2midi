"""Tests for the ``scripts/run.py`` command-line helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run  # noqa: E402


def test_channel_1_maps_to_mido_zero():
    assert run.midi_channel(1) == 0


def test_channel_16_maps_to_mido_15():
    assert run.midi_channel(16) == 15


def test_channel_0_means_spread():
    assert run.midi_channel(0) is None


def test_channel_out_of_range_is_rejected():
    for bad in (-1, 17, 99):
        with pytest.raises(ValueError):
            run.midi_channel(bad)


def test_default_channel_is_one():
    args = run.parse_args([])
    assert run.midi_channel(args.channel) == 0


def test_default_min_magnitude_plays_everything():
    # The feed's own floor is about M0.8, so 0.0 means "no threshold of
    # ours" and plays every event the feed has.
    assert run.parse_args([]).min_magnitude == 0.0


def test_status_page_failure_does_not_stop_the_bridge(monkeypatch, tmp_path):
    # A taken status port used to make run.py exit before playing anything.
    # The page is a convenience; the bridge must still run.
    import q2m.state as state_mod

    class Boom:
        def __init__(self, *a, **k):
            pass

        def start(self):
            raise OSError(48, "Address already in use")

    monkeypatch.setattr(state_mod, "StatusServer", Boom)
    monkeypatch.setattr(run.midi, "open_output", lambda name=None: _NullSink())
    monkeypatch.setattr(run.midi, "list_output_ports", lambda: ["fake"])
    monkeypatch.setattr(run.core, "run_forever", lambda *a, **k: None)
    monkeypatch.setattr(run.state, "State", lambda root: _NullState())

    rc = run.main(["--port", "fake"])
    assert rc == 0


class _NullSink:
    def send(self, msg):
        pass

    def close(self):
        pass


class _NullState:
    def set_port(self, name):
        pass

    def snapshot(self):
        return {}
