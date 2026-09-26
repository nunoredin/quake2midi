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


def test_small_events_are_one_to_three_notes():
    for mag in (0.8, 1.5, 2.9):
        count = len(mapping.map_event(event(mag=mag)))
        assert mapping._SMALL_NOTES[0] <= count <= mapping._SMALL_NOTES[1]


def test_small_events_are_brief():
    # A tiny flash, not a gesture.
    for mag in (0.8, 2.0, 2.9):
        note = mapping.map_event(event(mag=mag))[0]
        assert note.duration_ms <= mapping._SMALL_DURATION_MS[1]
        assert note.velocity <= mapping._SMALL_VELOCITY[1]


def test_medium_events_are_unstable():
    # Several notes, and the pitch moves: not a rising run.
    notes = mapping.map_event(event(mag=4.0, id="a"))
    assert len(notes) >= mapping._MEDIUM_NOTES[0]
    pitches = [n.note for n in notes]
    assert len(set(pitches)) > 1
    gaps = [b - a for a, b in zip(pitches, pitches[1:])]
    assert any(g != gaps[0] for g in gaps)


def test_medium_timing_is_uneven():
    notes = mapping.map_event(event(mag=4.0, id="b"))
    steps = [b.delay_ms - a.delay_ms for a, b in zip(notes, notes[1:])]
    assert len(set(steps)) > 1


def test_hard_events_are_long_and_strong():
    for mag in (5.0, 6.0, 7.0):
        notes = mapping.map_event(event(mag=mag, id="c"))
        assert len(notes) >= mapping._HARD_NOTES[0]
        assert all(n.velocity >= mapping._HARD_VELOCITY[0] for n in notes)
        assert all(n.duration_ms >= mapping._HARD_DURATION_MS[0]
                   for n in notes)


def test_harder_is_always_louder_and_longer():
    # The regimes must not overlap, or a harder quake could come out
    # quieter or shorter than a weaker one.
    small = mapping.map_event(event(mag=2.5, id="s"))[0]
    medium = mapping.map_event(event(mag=4.0, id="m"))[0]
    hard = mapping.map_event(event(mag=6.0, id="h"))[0]
    assert small.velocity < medium.velocity < hard.velocity
    assert small.duration_ms < medium.duration_ms < hard.duration_ms


def test_hard_events_have_more_notes_than_small():
    small = mapping.map_event(event(mag=1.0, id="s"))
    hard = mapping.map_event(event(mag=6.0, id="h"))
    assert len(hard) > len(small)


def test_different_events_sound_different():
    # Two medium events must not come out identical, or "unstable" fails.
    shapes = {
        tuple((n.note, n.velocity, n.delay_ms)
              for n in mapping.map_event(event(mag=4.0, id=f"e{i}")))
        for i in range(20)
    }
    assert len(shapes) > 1


def test_gesture_is_stable_for_one_event_id():
    # Randomness is seeded from the id, so a replay is reproducible.
    a = mapping.map_event(event(mag=4.0, id="same"))
    b = mapping.map_event(event(mag=4.0, id="same"))
    assert a == b


def test_seed_ignores_process_salting():
    # hash() is salted per process; the seed must not be.
    assert mapping._seed({"id": "abc"}) == mapping._seed({"id": "abc"})
    assert mapping._seed({"id": "abc"}) != mapping._seed({"id": "xyz"})


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
    assert len(notes) >= 1


def test_map_event_grows_with_magnitude():
    small = mapping.map_event(event(mag=0.8))
    large = mapping.map_event(event(mag=7.0))
    assert len(large) > len(small)
    assert large[0].velocity > small[0].velocity


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


def test_gestures_leave_the_pentatonic_scale():
    # Chaos means the pentatonic anchor is broken: across many events, some
    # note must land on an interval the scale does not contain.
    scale = set(mapping._SCALE)
    offsets = set()
    for i in range(40):
        notes = mapping.map_event(event(mag=4.0, id=f"c{i}"))
        base = mapping._ROOT_NOTE + mapping._SCALE[
            mapping._pitch_index(0.0)
        ]
        offsets.update(n.note - base for n in notes)
    assert offsets - scale


def test_gestures_span_more_than_one_octave():
    # Octave jumps mean a single gesture can cover a wide register.
    spans = []
    for i in range(40):
        notes = mapping.map_event(event(mag=6.0, id=f"o{i}"))
        spans.append(max(n.note for n in notes) - min(n.note for n in notes))
    assert max(spans) > 12


def test_small_gestures_can_also_clash():
    # The small regime is chaotic too, not a single clean note.
    shapes = {
        tuple((n.note, n.delay_ms)
              for n in mapping.map_event(event(mag=1.0, id=f"s{i}")))
        for i in range(40)
    }
    assert len(shapes) > 1
    assert any(len(shape) > 1 for shape in shapes)