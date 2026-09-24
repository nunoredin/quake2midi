"""Tests for :mod:`q2m.quakes`, with the network stubbed out."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse

import pytest

from q2m import quakes


class FakeResponse:
    """A stand-in for ``urlopen``'s return value."""

    def __init__(self, body: bytes) -> None:
        """Wrap ``body`` as a readable response."""
        self._body = body

    def __enter__(self) -> "FakeResponse":
        """Enter the context manager."""
        return self

    def __exit__(self, *exc: object) -> bool:
        """Exit the context manager without suppressing anything."""
        return False

    def read(self) -> bytes:
        """Return the body."""
        return self._body


def geo_json(*features: dict) -> bytes:
    """Return a GeoJSON payload with the given features."""
    return json.dumps({"type": "FeatureCollection",
                       "features": list(features)}).encode()


def a_feature(**overrides: object) -> dict:
    """Return one GeoJSON feature, with ``overrides`` applied."""
    base = {
        "id": "abc",
        "properties": {
            "time": "2026-06-21T00:00:00Z",
            "mag": 4.2,
            "flynn_region": "SOMEWHERE",
        },
        "geometry": {"coordinates": [1.0, 2.0, 3.0]},
    }
    base.update(overrides)
    return base


def patch(monkeypatch, result) -> dict:
    """Patch ``urlopen`` to return ``result`` (or raise it)."""
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)

    monkeypatch.setattr(quakes.urllib.request, "urlopen", fake_urlopen)
    return captured


def test_parses_a_feature(monkeypatch):
    patch(monkeypatch, geo_json(a_feature()))
    events = quakes.fetch_live_earthquakes(4.0)
    assert len(events) == 1
    event = events[0]
    assert event["id"] == "abc"
    assert event["mag"] == 4.2
    assert event["lat"] == 2.0
    assert event["lon"] == 1.0
    assert event["depth"] == 3.0
    assert event["region"] == "SOMEWHERE"


def test_missing_depth_becomes_none(monkeypatch):
    feature = a_feature(geometry={"coordinates": [1.0, 2.0]})
    patch(monkeypatch, geo_json(feature))
    events = quakes.fetch_live_earthquakes(4.0)
    assert events[0]["depth"] is None


def test_properties_depth_wins_over_coordinates(monkeypatch):
    # The live feed puts the true, positive depth in properties.depth and a
    # negative elevation in coordinates[2]. The properties value wins.
    feature = a_feature(geometry={"coordinates": [95.7, 5.2, -10.0]})
    feature["properties"]["depth"] = 10.0
    patch(monkeypatch, geo_json(feature))
    assert quakes.fetch_live_earthquakes(4.0)[0]["depth"] == 10.0


def test_negative_elevation_becomes_positive_depth(monkeypatch):
    # Without properties.depth, the GeoJSON elevation is flipped: it is
    # negative downwards, but depth is reported positive.
    feature = a_feature(geometry={"coordinates": [1.0, 2.0, -48.5]})
    patch(monkeypatch, geo_json(feature))
    assert quakes.fetch_live_earthquakes(4.0)[0]["depth"] == 48.5


def test_request_asks_for_the_right_parameters(monkeypatch):
    captured = patch(monkeypatch, geo_json())
    quakes.fetch_live_earthquakes(5.5)
    query = urllib.parse.parse_qs(
        urllib.parse.urlparse(captured["url"]).query
    )
    assert query["minmagnitude"] == ["5.5"]
    assert query["format"] == ["json"]
    assert query["orderby"] == ["time-asc"]
    assert captured["timeout"] == quakes.EQ_FETCH_TIMEOUT_S


def test_lookback_defaults_to_a_window_wider_than_the_publication_lag():
    # The feed publishes an event up to ~21 minutes after it happens, and
    # ``start`` filters on origin time, so the window must be comfortably
    # wider than the poll interval.
    assert quakes.EQ_LOOKBACK_S >= 40 * 60


def test_lookback_is_honoured(monkeypatch):
    from datetime import datetime, timezone

    captured = patch(monkeypatch, geo_json())
    quakes.fetch_live_earthquakes(4.0, lookback_s=90 * 60)
    query = urllib.parse.parse_qs(
        urllib.parse.urlparse(captured["url"]).query
    )
    start = datetime.strptime(query["start"][0], "%Y-%m-%dT%H:%M:%S")
    start = start.replace(tzinfo=timezone.utc)
    age_min = (datetime.now(timezone.utc) - start).total_seconds() / 60
    assert 88 <= age_min <= 92


def test_http_204_is_an_empty_list(monkeypatch):
    err = urllib.error.HTTPError("u", 204, "no content", {}, None)
    patch(monkeypatch, err)
    assert quakes.fetch_live_earthquakes(4.0) == []


def test_other_http_errors_propagate(monkeypatch):
    err = urllib.error.HTTPError("u", 500, "boom", {}, None)
    patch(monkeypatch, err)
    with pytest.raises(urllib.error.HTTPError):
        quakes.fetch_live_earthquakes(4.0)


def test_empty_body_is_an_empty_list(monkeypatch):
    patch(monkeypatch, b"   ")
    assert quakes.fetch_live_earthquakes(4.0) == []


def test_non_object_json_is_rejected(monkeypatch):
    patch(monkeypatch, b"[]")
    with pytest.raises(ValueError):
        quakes.fetch_live_earthquakes(4.0)


def test_incomplete_features_are_skipped(monkeypatch):
    good = a_feature(id="keep")
    no_mag = a_feature(id="no-mag")
    del no_mag["properties"]["mag"]
    short_coords = a_feature(id="short", geometry={"coordinates": [1.0]})
    patch(monkeypatch, geo_json(good, no_mag, short_coords))
    events = quakes.fetch_live_earthquakes(4.0)
    assert [e["id"] for e in events] == ["keep"]


def test_id_falls_back_to_unid(monkeypatch):
    feature = a_feature()
    del feature["id"]
    feature["properties"]["unid"] = "from-props"
    patch(monkeypatch, geo_json(feature))
    assert quakes.fetch_live_earthquakes(4.0)[0]["id"] == "from-props"


def test_region_falls_back_to_region_key(monkeypatch):
    feature = a_feature()
    del feature["properties"]["flynn_region"]
    feature["properties"]["region"] = "PLAIN REGION"
    patch(monkeypatch, geo_json(feature))
    assert quakes.fetch_live_earthquakes(4.0)[0]["region"] == "PLAIN REGION"