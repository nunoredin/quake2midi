"""MIDI port selection and note output.

Everything here is local: we list the available output ports, pick one by
name, and send notes to it. When no port is wanted (``--dry-run``) we use a
null sink that prints instead, so the rest of the code does not care.
"""

from __future__ import annotations

import sys

import mido

# All Sound Off (CC 120) and All Notes Off (CC 123).
_ALL_SOUND_OFF = 120
_ALL_NOTES_OFF = 123
_CHANNELS = 16


def list_output_ports() -> list[str]:
    """Return the names of the available MIDI output ports."""
    return list(mido.get_output_names())


def all_notes_off(sink) -> None:
    """Silence every channel, so nothing is left hanging.

    Sends All Sound Off and All Notes Off on all 16 channels. Ports that
    accept only one channel raise on the others; those failures are ignored
    on purpose, since the goal is only to stop stuck notes.

    Args:
        sink: Anything with ``send(msg)``.
    """
    for control in (_ALL_SOUND_OFF, _ALL_NOTES_OFF):
        for channel in range(_CHANNELS):
            try:
                sink.send(mido.Message(
                    "control_change",
                    channel=channel,
                    control=control,
                    value=0,
                ))
            except (ValueError, OSError):
                continue


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
        """Print one message and count it.

        Control changes are counted but not printed: the all-notes-off
        panic sends sixteen of them, and they would drown the notes.

        Args:
            msg: The message to send.
        """
        self.sent += 1
        if msg.type != "control_change":
            print(f"  midi  {msg}", file=sys.stdout, flush=True)

    def close(self) -> None:
        """Do nothing; there is no port to close."""