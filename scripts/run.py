#!/usr/bin/env python3
"""Run the quake2midi bridge.

Examples:
    python scripts/run.py --list-ports
    python scripts/run.py --once --dry-run
    python scripts/run.py --min-magnitude 5.0
    python scripts/run.py --port "IAC Driver Bus 1"

The status page is served at http://127.0.0.1:5446/ unless ``--once`` is set.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from q2m import core, midi, quakes, state  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Argument list, or None for ``sys.argv[1:]``.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Turn live earthquakes into MIDI notes.",
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="list MIDI output ports and exit",
    )
    parser.add_argument(
        "--port",
        default=None,
        help="MIDI output port name (default: the first one)",
    )
    parser.add_argument(
        "--min-magnitude",
        type=float,
        default=core.DEFAULT_MIN_MAGNITUDE,
        help="FDSN magnitude floor (default: %(default)s)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=core.POLL_INTERVAL_S,
        help="seconds between polls (default: %(default)s)",
    )
    parser.add_argument(
        "--lookback",
        type=float,
        default=quakes.EQ_LOOKBACK_S,
        help=(
            "seconds of history each fetch asks for; must cover the feed's "
            "publication lag (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--channel",
        type=int,
        default=1,
        help=(
            "MIDI channel to send on, 1-16 (default: %(default)s). "
            "Use 0 to spread events across eight channels by longitude"
        ),
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help=(
            "mark the events already in the lookback window as seen "
            "instead of playing them at start-up"
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="poll once and exit; do not serve the status page",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the notes instead of sending them",
    )
    parser.add_argument(
        "--no-status",
        action="store_true",
        help="do not serve the status page",
    )
    return parser.parse_args(argv)


def midi_channel(value: int) -> int | None:
    """Convert a 1-16 channel number to mido's 0-15, or None to spread.

    Args:
        value: The channel as given on the command line. 0 means "spread
            events across eight channels by longitude".

    Returns:
        A mido channel, 0-15, or None.

    Raises:
        ValueError: The value is outside 0-16.
    """
    if value == 0:
        return None
    if 1 <= value <= 16:
        return value - 1
    raise ValueError(f"channel must be 0-16, got {value}")


def main(argv: list[str] | None = None) -> int:
    """Run the bridge. Returns a process exit code."""
    args = parse_args(argv)

    try:
        channel = midi_channel(args.channel)
    except ValueError as err:
        print(f" [fail] {err}")
        return 2

    if args.list_ports:
        names = midi.list_output_ports()
        if not names:
            print(" no MIDI output ports found")
            print(
                " enable IAC (macOS), snd-virmidi (Linux), or loopMIDI "
                "(Windows) - see AGENTS.md"
            )
            return 1
        for name in names:
            print(f" {name}")
        return 0

    base = Path(__file__).resolve().parents[1]
    st = state.State(base)

    if args.dry_run:
        sink = midi.DryRunSink()
        st.set_port("dry-run")
        print(" [ ok ] dry run: no MIDI port will be opened")
    else:
        try:
            sink = midi.open_output(args.port)
        except RuntimeError as err:
            print(f" [fail] {err}")
            return 1
        st.set_port(args.port or "default")

    player = core.Player(sink)
    # Clear anything a previous run left sounding on this port.
    player.panic()

    if args.once:
        played = core.run_once(
            player, st, args.min_magnitude, set(), dry_run=args.dry_run,
            lookback_s=int(args.lookback), channel=channel,
        )
        print(f" done: played {played} event(s)")
        sink.close()
        return 0

    server = None
    if not args.no_status:
        try:
            server = state.StatusServer(st).start()
        except OSError as err:
            # The status page is a convenience; the bridge is the point.
            # A taken port must not stop the music.
            print(f" [warn] status page unavailable: {err}")
            print("        the bridge will run without it")
        else:
            print(f" status: http://{state.HOST}:{state.PORT}/")

    try:
        core.run_forever(
            player, st, args.min_magnitude, args.interval,
            lookback_s=int(args.lookback),
            skip_existing=args.skip_existing,
            channel=channel,
        )
    except KeyboardInterrupt:
        print("\n stopped")
    finally:
        if server is not None:
            server.shutdown()
        sink.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())