# quake2midi

**Live earthquakes, turned into MIDI.**

Every time the Earth shakes somewhere above your magnitude floor, quake2midi
plays it. It polls the EMSC / SeismicPortal FDSN feed, and maps each new
event to a short gesture of MIDI notes on a local port. Magnitude sets how
loud and how long, latitude picks the pitch on a pentatonic scale, and depth
drops the octave. Point a DAW or a synth at the port, leave it running, and
the planet plays.

## Run it

The quickest way, once setup has run:

- **macOS** — double-click [`quake2midi.command`](quake2midi.command).
- **Windows** — double-click [`quake2midi.bat`](quake2midi.bat).

Either one checks the venv, lists your MIDI destinations, and starts the
bridge. Then open http://127.0.0.1:5446/ to watch the last events and the
notes sent.

From a terminal, the same thing in three steps:

```
python3 scripts/setup.py                 # once: venv + dependencies
.venv/bin/python scripts/run.py \
  --list-ports                           # find your MIDI destination
.venv/bin/python scripts/run.py \
  --port "IAC Driver Bus 1"              # or just run it
```

First time here? Follow [Setup](AGENTS.md#setup) in `AGENTS.md`.

## Hearing it

The bridge sends MIDI to a port; something has to listen on the other side.
On macOS the usual destination is the IAC Driver. A DAW track, a synth, or a
VCV Rack **MIDI to CV** module patched to an oscillator will do. Point it at
the port named by `--list-ports`, on **channel 1**.

If nothing sounds, check in this order: the listener is on the same port, it
is on channel 1, and `--min-magnitude` is low enough that events are arriving.

## Without a MIDI port

Nothing is needed to try the mapping:

```
.venv/bin/python scripts/run.py --once --dry-run
```

This fetches the feed once, prints the notes it would send, and exits.

## Tests

```
.venv/bin/python -m pytest
```

The tests stub the network and the MIDI port, so they run anywhere. Install
the dev extras with `.venv/bin/python -m pip install pytest ruff`.

## The specs

| | |
|---|---|
| Source | EMSC / SeismicPortal FDSN, polled every 8 s, six-hour window |
| Mapping | Magnitude → velocity, length, note count; latitude → pitch; depth → octave |
| Output | MIDI notes on channel 1 by default, to one local output port |
| Runs on | Python 3.11+, `mido`, `python-rtmidi`. A standard-library status page on `127.0.0.1:5446` |

The window is much wider than the poll interval on purpose: the feed
publishes an event well after it happens, and the FDSN `start` filter works
on origin time, so a narrow window drops late events permanently. The
magnitude floor is 0.0 — the feed's own floor is about M0.8, so this plays
everything it has, roughly 16 events an hour worldwide. At start-up the
events already in the window are played, so sound begins immediately; pass
`--skip-existing` to wait for new ones instead.

## What is in the box

- [`q2m/`](q2m/) — the package. Start with [`q2m/README.md`](q2m/README.md).
- [`scripts/`](scripts/) — `setup.py` and the `run.py` entry point.
- [`AGENTS.md`](AGENTS.md) — how to build on it with an AI assistant.
- [`NOTICE`](NOTICE) — data sources and third-party licences.

## License

MIT ([`LICENSE`](LICENSE)). Third-party notices: [`NOTICE`](NOTICE).