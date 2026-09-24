# quake2midi

**Live earthquakes, turned into MIDI.**

Every time the Earth shakes somewhere above your magnitude floor, quake2midi
plays it. It polls the EMSC / SeismicPortal FDSN feed, and maps each new
event to a short gesture of MIDI notes on a local port. Magnitude sets how
loud and how long, latitude picks the pitch on a pentatonic scale, and depth
drops the octave. Point a DAW or a synth at the port, leave it running, and
the planet plays.

## Run it

```
python3 scripts/setup.py                 # once: venv + dependencies
.venv/bin/python scripts/run.py \
  --list-ports                           # find your MIDI destination
.venv/bin/python scripts/run.py \
  --port "IAC Driver Bus 1"              # or just run it
```

Then open http://127.0.0.1:5446/ to watch the last events and the notes sent.

First time here? Follow [Setup](AGENTS.md#setup) in `AGENTS.md`.

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
| Source | EMSC / SeismicPortal FDSN, polled every 8 s, one-hour window |
| Mapping | Magnitude → velocity, length, note count; latitude → pitch; depth → octave; longitude → channel |
| Output | MIDI notes to one local output port |
| Runs on | Python 3.11+, `mido`, `python-rtmidi`. A standard-library status page on `127.0.0.1:5446` |

The window is wider than the poll interval on purpose: the feed publishes an
event up to ~21 minutes after it happens, and the FDSN `start` filter works
on origin time. At start-up the existing events are marked as seen rather
than played; pass `--play-existing` to hear the last hour instead.

## What is in the box

- [`q2m/`](q2m/) — the package. Start with [`q2m/README.md`](q2m/README.md).
- [`scripts/`](scripts/) — `setup.py` and the `run.py` entry point.
- [`AGENTS.md`](AGENTS.md) — how to build on it with an AI assistant.
- [`NOTICE`](NOTICE) — data sources and third-party licences.

## License

MIT ([`LICENSE`](LICENSE)). Third-party notices: [`NOTICE`](NOTICE).