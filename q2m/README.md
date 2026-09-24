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
| `midi.py` | `list_output_ports()`, `open_output()`, `all_notes_off()`, `DryRunSink` |
| `core.py` | `Player`, `prime_seen()`, `run_once()` and `run_forever()` |
| `state.py` | `State` and `StatusServer` — the status file and page |

## The lookback window

`fetch_live_earthquakes()` asks for the last six hours by default. That is
much wider than the 8-second poll interval, and deliberately so: the feed
publishes an event well after it happens (median lag between origin time and
`lastupdate`: ~13 min for M2.5+, ~32 min for smaller events), while the FDSN
`start` filter applies to **origin time**. A window sized to the poll
interval drops every late event permanently. Six hours catches the bulk: a
one-hour window saw 4 events where six hours saw 68.

The cost is that the first fetch of a run returns hours of history. By
default `run_forever()` plays it, so the bridge makes sound from the first
second. Pass `--skip-existing` to call `prime_seen()` instead, which marks
those ids as already played and waits for new ones. The window is settable
with `--lookback SECONDS`.

## The mapping

`map_event()` reads three fields and ignores the rest:

- **Magnitude** (0.5 to 7, clamped) sets velocity (35-127), the held
  duration (120-900 ms), and how many notes the gesture has (1-5). The floor
  sits just below the feed's own ~M0.8, so small events still get dynamics
  instead of all clamping to the minimum.
- **Latitude** picks an index into a two-octave A-minor pentatonic.
- **Depth** shifts the octave: shallow up, deep down. A missing depth is 0.

Notes in a gesture are staggered a few tens of milliseconds apart, so a big
event is a small run rather than a chord.

Everything goes to one MIDI channel (`DEFAULT_CHANNEL`), because a synth
patch or a VCV Rack MIDI-to-CV module usually listens on a single channel.
Pass `channel=None` to `map_event()` — `--channel 0` on the command line — to
spread events across eight channels by longitude and magnitude instead.

## Adding a destination

`midi.py` opens any port `mido` can see. Pass `--port NAME` to pick one; the
default is the first port in the list. `DryRunSink` is a drop-in that prints,
which is what `--dry-run` uses.

## Stuck notes

A note-on with no matching note-off leaves a tone sounding forever. The
`Player` prevents that: it tracks the notes it has turned on but not off, and
`Player.panic()` releases exactly those, then sends All Sound Off (CC 120)
and All Notes Off (CC 123) on all 16 channels. The panic runs when a gesture
is interrupted, when `run_forever()` stops, and once at start-up to clear
anything a previous run left behind.

## Tests

```
.venv/bin/python -m pytest
```

The tests stub the network and the MIDI port, so they run anywhere. Install
them with `.venv/bin/python -m pip install pytest ruff`.

## Conventions

Python follows Google style: 80 columns, 4 spaces, Google docstrings. `ruff`
is configured in `pyproject.toml`.