# q2m

The package behind quake2midi. Five modules, one direction of flow:

```
quakes.py  ->  mapping.py  ->  midi.py
                    ^
                 core.py  ->  state.py
```

| Module | What it does |
|---|---|
| `quakes.py` | `fetch_live_earthquakes()` — one poll of the FDSN feed |
| `mapping.py` | `map_event()` — an event dict in, a list of `Note` out |
| `midi.py` | `list_output_ports()`, `open_output()`, `DryRunSink` |
| `core.py` | `run_once()` and `run_forever()` — the loop |
| `state.py` | `State` and `StatusServer` — the status file and page |

## The mapping

`map_event()` reads three fields and ignores the rest:

- **Magnitude** (2 to 7, clamped) sets velocity (35-127), the held duration
  (120-900 ms), and how many notes the gesture has (1-5).
- **Latitude** picks an index into a two-octave A-minor pentatonic.
- **Depth** shifts the octave: shallow up, deep down. A missing depth is 0.
- **Longitude** and magnitude together choose one of eight channels.

Notes in a gesture are staggered a few tens of milliseconds apart, so a big
event is a small run rather than a chord.

## Adding a destination

`midi.py` opens any port `mido` can see. Pass `--port NAME` to pick one; the
default is the first port in the list. `DryRunSink` is a drop-in that prints,
which is what `--dry-run` uses.

## Conventions

Python follows Google style: 80 columns, 4 spaces, Google docstrings. `ruff`
is configured in `pyproject.toml`.