#!/usr/bin/env python3
"""
Run Snappix cross-platform guard tests, then the full suite.

Use before GitHub upload so Linux and Windows contracts stay green on the
current host. CI also runs these checks on ubuntu and windows-latest.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_MODULES = [
    "tests.test_cross_platform_contract",
    "tests.test_paths",
    "tests.test_os_compatibility_matrix",
    "tests.test_win32_window",
    "tests.test_video_recorder",
]


def _python() -> str:
    if sys.platform == "win32":
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python3"
        if not candidate.exists():
            candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate if candidate.exists() else Path(sys.executable))


def main() -> int:
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("PYTHONWARNINGS", "ignore")
    python = _python()

    print(f"== Cross-platform contract ({sys.platform}) ==")
    contract = subprocess.run(
        [python, "-m", "unittest", *CONTRACT_MODULES, "-v"],
        cwd=ROOT,
        env=env,
        check=False,
    )
    if contract.returncode != 0:
        return contract.returncode

    print("== Full test suite ==")
    full = subprocess.run(
        [python, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        env=env,
        check=False,
    )
    return full.returncode


if __name__ == "__main__":
    raise SystemExit(main())
