#!/usr/bin/env python3
"""Create the repo ``.venv`` and install quake2midi's dependencies."""

from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

MIN_PYTHON = (3, 11)
DEPS = ["mido>=1.3", "python-rtmidi>=1.5"]


def root() -> Path:
    """Return the repository root (parent of ``scripts/``)."""
    return Path(__file__).resolve().parents[1]


def venv_python(venv_dir: Path) -> Path:
    """Return the interpreter inside ``venv_dir`` for this platform."""
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def main() -> int:
    """Run setup. Returns a process exit code."""
    if sys.version_info < MIN_PYTHON:
        need = ".".join(str(p) for p in MIN_PYTHON)
        have = ".".join(str(p) for p in sys.version_info[:3])
        print(f" [fail] Python {need}+ needed, found {have}")
        return 1

    base = root()
    venv_dir = base / ".venv"
    if not venv_dir.exists():
        print(f" [ ok ] creating {venv_dir.name}/")
        venv.EnvBuilder(with_pip=True).create(venv_dir)
    else:
        print(f" [skip] {venv_dir.name}/ already exists")

    py = venv_python(venv_dir)
    if not py.exists():
        print(f" [fail] missing interpreter at {py}")
        return 1

    print(" [ ok ] installing dependencies")
    result = subprocess.run(
        [str(py), "-m", "pip", "install", "--upgrade", "pip", *DEPS],
        cwd=base,
        check=False,
    )
    if result.returncode != 0:
        print(" [fail] pip install failed; see the output above")
        return result.returncode

    check = subprocess.run(
        [str(py), "-c", "import mido, rtmidi"],
        cwd=base,
        check=False,
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        print(" [fail] mido or rtmidi did not import after install")
        print(check.stderr.strip())
        return check.returncode

    print(f" Done. Run: {py} scripts/run.py --list-ports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())