"""Fetch live EMSC / SeismicPortal earthquake events.

The FDSN event service is the same one SeismicPortal uses for its web map.
Each poll asks for the last few minutes of worldwide events at or above a
magnitude cutoff and returns them as plain dicts.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

EQ_QUERY_URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
EQ_LOOKBACK_S = 20 * 60
EQ_FETCH_TIMEOUT_S = 8
_UA = "quake2midi/1"


def fetch_live_earthquakes(min_magnitude: float) -> list[dict]:
    """Return worldwide events at or above ``min_magnitude``.

    Args:
        min_magnitude: FDSN ``minmagnitude`` cutoff.

    Returns:
        Event dicts with ``id``, ``time``, ``mag``, ``lat``, ``lon``,
        ``depth``, and ``region``. An HTTP 204 is an empty list.

    Raises:
        OSError: Network failure other than 204.
        ValueError: Response is not JSON GeoJSON.
    """
    since = datetime.now(timezone.utc) - timedelta(seconds=EQ_LOOKBACK_S)
    params = {
        "start": since.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": min_magnitude,
        "format": "json",
        "orderby": "time-asc",
    }
    url = EQ_QUERY_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=EQ_FETCH_TIMEOUT_S) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as err:
        if err.code == 204:
            return []
        raise
    if not raw or not raw.strip():
        return []
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("live quake response must be a JSON object")
    events = []
    for feat in data.get("features") or []:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        depth = coords[2] if len(coords) > 2 else None
        time_str, mag = props.get("time"), props.get("mag")
        eid = feat.get("id") or props.get("unid")
        if time_str is None or mag is None or eid is None:
            continue
        events.append({
            "id": str(eid),
            "time": time_str,
            "mag": float(mag),
            "lat": float(lat),
            "lon": float(lon),
            "depth": float(depth) if depth is not None else None,
            "region": (
                props.get("flynn_region") or props.get("region") or ""
            ),
        })
    return events