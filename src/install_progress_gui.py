"""
Tkinter progress dialog for first-time dependency installation.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTALLER_SCRIPT = PROJECT_ROOT / "install_dependencies.py"


def map_installer_line_to_status(line: str) -> str | None:
    """
    Maps installer log output to user-facing status text.

    Args:
        line: Installer stdout/stderr line.

    Returns:
        str | None: Status text or None.
    """

    normalized = line.strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    if "installing system dependencies" in lowered:
        return "Installing Linux system packages (sudo may be required)..."
    if "requesting administrator rights via pkexec" in lowered:
        return "Waiting for administrator password dialog..."
    if "creating virtual environment" in lowered:
        return "Creating Python virtual environment..."
    if "installing dependencies" in lowered:
        return "Installing Python packages (PySide6, Pillow, requests)..."
    if "done." in lowered:
        return "Installation complete. Starting Snappix..."
    if "error" in lowered or "warning" in lowered:
        return normalized
    return None


def _monitor_geometry_for_point(x_pos: int, y_pos: int) -> tuple[int, int, int, int] | None:
    """
    Resolves monitor geometry containing the given pointer position.

    Args:
        x_pos: Global pointer X coordinate.
        y_pos: Global pointer Y coordinate.

    Returns:
        tuple[int, int, int, int] | None: (x, y, width, height) or None.
    """

    try:
        output = subprocess.run(
            ["xrandr", "--listmonitors"],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.5,
        ).stdout
    except Exception:
        return None

    geometry_pattern = re.compile(r"(\d+)/\d+x(\d+)/\d+\+(-?\d+)\+(-?\d+)")
    for line in output.splitlines():
        match = geometry_pattern.search(line)
        if match is None:
            continue
        width = int(match.group(1))
        height = int(match.group(2))
        monitor_x = int(match.group(3))
        monitor_y = int(match.group(4))
        if (
            monitor_x <= x_pos < monitor_x + width
            and monitor_y <= y_pos < monitor_y + height
        ):
            return (monitor_x, monitor_y, width, height)
    return None


def run_installer_with_progress_gui() -> int:
    """
    Runs dependency installer with visible setup window.

    Returns:
        int: Installer process exit code.
    """

    if not INSTALLER_SCRIPT.exists():
        messagebox.showerror("Snappix", "Installer script not found at install_dependencies.py")
        return 1

    root = tk.Tk()
    root.title("Snappix - First-time Setup")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    frame = ttk.Frame(root, padding=20)
    frame.grid(row=0, column=0, sticky="nsew")

    ttk.Label(
        frame,
        text=(
            "Snappix is installing required dependencies.\n"
            "Please wait — this may take a few minutes."
        ),
        justify="center",
    ).grid(row=0, column=0, pady=(0, 12))

    status_var = tk.StringVar(value="Preparing installation...")
    status_label = ttk.Label(frame, textvariable=status_var, wraplength=440, justify="center")
    status_label.grid(row=1, column=0, pady=(0, 12))

    progress = ttk.Progressbar(frame, mode="indeterminate", length=440)
    progress.grid(row=2, column=0, pady=(0, 8))
    progress.start(12)

    ttk.Label(
        frame,
        text="If prompted, enter your password in the terminal for system packages.",
        font=("", 9),
        foreground="#555555",
        wraplength=440,
        justify="center",
    ).grid(row=3, column=0)

    exit_code_holder: list[int] = [1]

    def run_installer() -> None:
        command = [sys.executable, str(INSTALLER_SCRIPT)]
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if process.stdout is None:
            exit_code_holder[0] = 1
            root.after(0, root.quit)
            return

        for line in process.stdout:
            status = map_installer_line_to_status(line)
            if status is not None:
                root.after(0, lambda message=status: status_var.set(message))

        process.wait()
        exit_code_holder[0] = process.returncode if process.returncode is not None else 1
        root.after(0, root.quit)

    threading.Thread(target=run_installer, daemon=True).start()

    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    pointer_x = root.winfo_pointerx()
    pointer_y = root.winfo_pointery()
    monitor_geometry = _monitor_geometry_for_point(pointer_x, pointer_y)
    if monitor_geometry is None:
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
    else:
        monitor_x, monitor_y, monitor_width, monitor_height = monitor_geometry
        x = monitor_x + ((monitor_width - width) // 2)
        y = monitor_y + ((monitor_height - height) // 2)
    root.geometry(f"+{x}+{y}")

    root.mainloop()
    progress.stop()
    exit_code = exit_code_holder[0]

    if exit_code != 0:
        messagebox.showerror(
            "Snappix",
            "Dependency installation failed.\n"
            "Check terminal output or run: python3 install_dependencies.py",
        )

    root.destroy()
    return exit_code
