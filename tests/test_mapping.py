"""Tests for the pure mapping functions in :mod:`q2m.mapping`."""

from __future__ import annotations

import pytest

from q2m import mapping


def event(**overrides: object) -> dict:
    """Return a minimal quake event, with ``overrides`` applied."""
    base = {
        "id": "test",
        "time": "2026-06-21T00:00:00Z",
        "mag": 4.0,
        "lat": 0.0,
        "lon": 0.0,
        "depth": None,
        "region": "TEST",
    }
    base.update(overrides)
    return base


def test_unit_clamps_below_and_above():
    assert mapping._unit(0.0) == 0.0
    assert mapping._unit(0.5) == 0.0
    assert mapping._unit(7.0) == 1.0
    assert mapping._unit(9.9) == 1.0


def test_unit_is_monotonic():
    values = [mapping._unit(m) for m in (0.5, 1.0, 2.0, 4.0, 6.0, 7.0)]
    assert values == sorted(values)


def test_small_events_are_not_all_clamped_to_the_minimum():
    # The feed's floor is about M0.8. With the mapping floor at 2.0 a fifth
    # of real events clamped to the minimum and came out identical.
    small = [mapping.map_event(event(mag=m))[0] for m in (0.8, 1.2, 1.6, 2.0)]
    assert len({n.velocity for n in small}) > 1


def test_pitch_index_spans_the_scale():
    assert mapping._pitch_index(-90.0) == 0
    assert mapping._pitch_index(90.0) == len(mapping._SCALE) - 1
    # Beyond the poles stays in range.
    assert mapping._pitch_index(-120.0) == 0
    assert mapping._pitch_index(120.0) == len(mapping._SCALE) - 1


def test_octave_shift_is_neutral_without_depth():
    assert mapping._octave_shift(None) == 0


def test_octave_shift_moves_down_with_depth():
    shallow = mapping._octave_shift(1.0)
    deep = mapping._octave_shift(700.0)
    assert shallow > deep
    assert {shallow, deep} <= {-12, 0, 12}


def test_channel_stays_in_range():
    for lon in (-180.0, -90.0, 0.0, 90.0, 180.0, 999.0):
        for mag in (1.0, 4.0, 9.0):
            channel = mapping._channel(lon, mag)
            assert 0 <= channel < 16


def test_map_event_defaults_to_one_channel():
    # A synth patch usually listens on a single channel, so events must not
    # be scattered across eight by default.
    for lon in (-180.0, -9.1, 0.0, 95.7, 180.0):
        notes = mapping.map_event(event(mag=4.5, lon=lon))
        assert {n.channel for n in notes} == {mapping.DEFAULT_CHANNEL}


def test_map_event_honours_an_explicit_channel():
    notes = mapping.map_event(event(mag=5.0), channel=9)
    assert {n.channel for n in notes} == {9}


def test_map_event_spreads_channels_when_asked():
    channels = {
        mapping.map_event(event(mag=4.5, lon=lon), channel=None)[0].channel
        for lon in (-180.0, -90.0, 0.0, 90.0, 180.0)
    }
    assert len(channels) > 1


def test_map_event_returns_at_least_one_note():
    notes = mapping.map_event(event(mag=0.8))
    assert len(notes) == 1


def test_map_event_grows_with_magnitude():
    small = mapping.map_event(event(mag=0.8))
    large = mapping.map_event(event(mag=7.0))
    assert len(large) >= len(small)
    assert large[0].velocity >= small[0].velocity


def test_map_event_notes_are_in_midi_range():
    for mag in (0.8, 4.5, 7.0):
        for lat in (-90.0, 0.0, 90.0):
            for depth in (None, 5.0, 800.0):
                notes = mapping.map_event(
                    event(mag=mag, lat=lat, depth=depth)
                )
                assert notes, (mag, lat, depth)
                for note in notes:
                    assert 0 <= note.note <= 127
                    assert 1 <= note.velocity <= 127
                    assert 0 <= note.channel <= 15
                    assert note.delay_ms >= 0
                    assert note.duration_ms > 0


def test_map_event_notes_are_ordered_by_delay():
    notes = mapping.map_event(event(mag=7.0))
    delays = [n.delay_ms for n in notes]
    assert delays == sorted(delays)


def test_map_event_is_deterministic():
    first = mapping.map_event(event(mag=5.5, lat=12.0, lon=34.0))
    second = mapping.map_event(event(mag=5.5, lat=12.0, lon=34.0))
    assert first == second


def test_map_event_requires_mag_and_lat():
    for missing in ("mag", "lat"):
        data = event()
        del data[missing]
        with pytest.raises(KeyError):
            mapping.map_event(data)


def test_map_event_needs_lon_only_when_spreading():
    # With a fixed channel, longitude plays no part in the mapping.
    data = event()
    del data["lon"]
    assert mapping.map_event(data)

    with pytest.raises(KeyError):
        mapping.map_event(data, channel=None)