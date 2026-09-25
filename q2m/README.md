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
| `core.py` | `Player`, `prime_seen()`, `run_once()`, `run_forever()`, `fake_event()` |
| `keys.py` | `KeyWatcher` — single keypresses, for the spacebar fake event |
| `state.py` | `State` and `StatusServer` — the status file and page |

## The spacebar

`run_forever()` can watch the terminal for the spacebar and play a fake M5
quake on each press, so a patch can be tested without waiting for a real
event. `KeyWatcher` puts the terminal into cbreak mode to read a key without
Enter, and restores it on every exit path — including `SIGTERM` and `SIGHUP`,
which would otherwise leave the shell with no echo. If stdin is not a
terminal the watcher declines and the bridge runs without it. No hint is
printed; the key is simply live.

## Nothing hangs

`run_forever()` watches the clock: if no event has played for
`silence_after_s` (30 s by default), it calls `Player.panic()` to force the
output back to silence. The longest gesture is under 4 s, so this is
comfortably clear of normal playing. Pass 0 to disable. The check runs
every half second, with or without a key watcher.

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

`map_event()` reads the magnitude as one of three regimes, and the regimes
are meant to be told apart by ear:

| Regime | Magnitude | Sounds like |
|---|---|---|
| Small | below M3 | A tiny flash: one note, 40-110 ms, quiet |
| Medium | M3 to M5 | Unstable: 3-7 notes that jump around, uneven timing and dynamics |
| Hard | M5 and up | Long and strong: 6-12 loud notes, each held 0.5-2 s, overlapping |

The velocity and duration ranges of the regimes **do not overlap**, so a
harder quake is always louder and longer than a weaker one. About 23% of the
feed is M0-2, 39% is M2-3, 28% is M3-4, 9% is M4-5, and 1% is M5+.

Beyond magnitude:

- **Latitude** picks an index into a two-octave A-minor pentatonic.
- **Depth** shifts the octave: shallow up, deep down. A missing depth is 0.

The medium and hard gestures are built from a random number generator seeded
from the event id (crc32, not `hash()`, which is salted per process). A given
event always sounds the same way, while different events differ.

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