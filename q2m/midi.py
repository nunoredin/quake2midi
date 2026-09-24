"""MIDI port selection and note output.

Everything here is local: we list the available output ports, pick one by
name, and send notes to it. When no port is wanted (``--dry-run``) we use a
null sink that prints instead, so the rest of the code does not care.
"""

from __future__ import annotations

import sys

import mido


def list_output_ports() -> list[str]:
    """Return the names of the available MIDI output ports."""
    return list(mido.get_output_names())


def open_output(name: str | None = None) -> "mido.ports.BaseOutput":
    """Open a MIDI output port.

    Args:
        name: Port name, or None to use mido's default.

    Returns:
        An open MIDI output port.

    Raises:
        RuntimeError: No output ports are available.
    """
    names = list_output_ports()
    if not names:
        raise RuntimeError(
            "no MIDI output ports; enable IAC (macOS), virmidi (Linux), "
            "or loopMIDI (Windows) - see AGENTS.md"
        )
    if name is not None:
        if name not in names:
            raise RuntimeError(
                f"MIDI port {name!r} not found; available: {names}"
            )
        return mido.open_output(name)
    return mido.open_output(names[0])


class DryRunSink:
    """A MIDI sink that prints notes instead of sending them."""

    def __init__(self) -> None:
        """Create the sink."""
        self.sent = 0

    def send(self, msg: "mido.Message") -> None:
        """Print one message and count it."""
        self.sent += 1
        print(f"  midi  {msg}", file=sys.stdout, flush=True)

    def close(self) -> None:
        """Do nothing; there is no port to close."""