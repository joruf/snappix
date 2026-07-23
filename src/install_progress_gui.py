"""
Tkinter progress dialog for first-time dependency installation.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTALLER_SCRIPT = PROJECT_ROOT / "install_dependencies.py"
SPLASH_LOGO_PATH = PROJECT_ROOT / "assets" / "snappix-splash.png"


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
    if "checking" in lowered or "detecting" in lowered:
        return _trim_status(normalized)
    if "installing system dependencies" in lowered:
        return "Installing Linux system packages…"
    if "requesting administrator rights via pkexec" in lowered:
        return "Waiting for administrator password dialog…"
    if "required system packages are present" in lowered:
        return "System packages ready — continuing setup…"
    if "trying recommended tools" in lowered:
        return "Checking recommended capture tools…"
    if "creating virtual environment" in lowered:
        return "Creating Python virtual environment…"
    if "installing dependencies" in lowered or "installing python" in lowered:
        return "Installing Python packages (PySide6, Pillow, requests, pynput)…"
    if "python packages installed" in lowered:
        return "Python packages installed…"
    if "done with warnings" in lowered:
        return "Setup finished with warnings — starting Snappix…"
    if "done." in lowered:
        return "Installation complete — starting Snappix…"
    if "error" in lowered or "warning" in lowered:
        return normalized
    if lowered.startswith("snappix installer:"):
        detail = normalized.split(":", 1)[-1].strip()
        if detail:
            return _trim_status(detail[0].upper() + detail[1:])
    return None


def _trim_status(text: str, max_length: int = 96) -> str:
    """
    Shortens long status strings for the splash label.

    Args:
        text: Raw status text.
        max_length: Maximum characters to keep.

    Returns:
        str: Possibly truncated status text.
    """

    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"


def summarize_installer_failure(log_lines: list[str], max_lines: int = 8) -> str:
    """
    Builds a short failure summary from installer log lines.

    Args:
        log_lines: Captured installer output lines.
        max_lines: Maximum number of trailing lines to include.

    Returns:
        str: User-facing failure details.
    """

    cleaned = [line.strip() for line in log_lines if line.strip()]
    if not cleaned:
        return "No installer output was captured."
    interesting = [
        line
        for line in cleaned
        if "error" in line.lower() or "warning" in line.lower() or "failed" in line.lower()
    ]
    selected = interesting[-max_lines:] if interesting else cleaned[-max_lines:]
    return "\n".join(selected)


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


def _load_splash_logo(parent: tk.Misc) -> tk.PhotoImage | None:
    """
    Loads the Snappix splash logo for the setup window.

    Args:
        parent: Tk widget that owns the image reference.

    Returns:
        tk.PhotoImage | None: Logo image when available.
    """

    if not SPLASH_LOGO_PATH.is_file():
        return None
    try:
        logo = tk.PhotoImage(file=str(SPLASH_LOGO_PATH), master=parent)
    except tk.TclError:
        return None
    # Keep a Python reference on the parent so Tk does not garbage-collect it.
    parent._snappix_splash_logo = logo  # type: ignore[attr-defined]
    return logo


def run_installer_with_progress_gui() -> int:
    """
    Runs dependency installer with a branded setup splash window.

    Returns:
        int: Installer process exit code.
    """

    if not INSTALLER_SCRIPT.exists():
        messagebox.showerror("Snappix", "Installer script not found at install_dependencies.py")
        return 1

    root = tk.Tk()
    root.title("Snappix")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(bg="#1a1f2a")

    frame = tk.Frame(root, bg="#1a1f2a", padx=36, pady=28)
    frame.grid(row=0, column=0, sticky="nsew")

    logo = _load_splash_logo(root)
    if logo is not None:
        logo_label = tk.Label(frame, image=logo, bg="#1a1f2a", borderwidth=0)
        logo_label.grid(row=0, column=0, pady=(4, 18))
    else:
        title = tk.Label(
            frame,
            text="Snappix",
            font=("Segoe UI", 28, "bold"),
            fg="#f4f8ff",
            bg="#1a1f2a",
        )
        title.grid(row=0, column=0, pady=(8, 18))

    brand = tk.Label(
        frame,
        text="Snappix",
        font=("Segoe UI", 18, "bold"),
        fg="#f4f8ff",
        bg="#1a1f2a",
    )
    brand.grid(row=1, column=0, pady=(0, 6))

    subtitle = tk.Label(
        frame,
        text="Checking installation…",
        font=("Segoe UI", 10),
        fg="#9aa6b8",
        bg="#1a1f2a",
    )
    subtitle.grid(row=2, column=0, pady=(0, 16))

    status_var = tk.StringVar(value="Preparing to verify dependencies…")
    status_label = tk.Label(
        frame,
        textvariable=status_var,
        font=("Segoe UI", 10),
        fg="#d7dee8",
        bg="#1a1f2a",
        wraplength=420,
        justify="center",
    )
    status_label.grid(row=3, column=0, pady=(0, 14))

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Snappix.Horizontal.TProgressbar",
        troughcolor="#2a3344",
        background="#4a9de8",
        bordercolor="#2a3344",
        lightcolor="#4a9de8",
        darkcolor="#2f7dd1",
        thickness=8,
    )
    progress = ttk.Progressbar(
        frame,
        mode="indeterminate",
        length=420,
        style="Snappix.Horizontal.TProgressbar",
    )
    progress.grid(row=4, column=0, pady=(0, 14))
    progress.start(14)

    hint = tk.Label(
        frame,
        text=(
            "If an administrator dialog appears, confirm it to install system packages.\n"
            "Python packages are installed into a local .venv."
        ),
        font=("Segoe UI", 9),
        fg="#7f8b9c",
        bg="#1a1f2a",
        wraplength=420,
        justify="center",
    )
    hint.grid(row=5, column=0)

    exit_code_holder: list[int] = [1]
    log_lines: list[str] = []

    def set_status(message: str) -> None:
        status_var.set(message)
        lowered = message.lower()
        if "complete" in lowered or "starting snappix" in lowered:
            subtitle.configure(text="Ready")
        elif "warning" in lowered or "error" in lowered:
            subtitle.configure(text="Setup notice")
        else:
            subtitle.configure(text="Checking installation…")

    def run_installer() -> None:
        command = [sys.executable, "-u", str(INSTALLER_SCRIPT)]
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        root.after(0, lambda: set_status("Checking system packages…"))
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
        )
        if process.stdout is None:
            exit_code_holder[0] = 1
            root.after(0, root.quit)
            return

        for line in process.stdout:
            log_lines.append(line.rstrip("\n"))
            status = map_installer_line_to_status(line)
            if status is not None:
                root.after(0, lambda message=status: set_status(message))

        process.wait()
        exit_code_holder[0] = process.returncode if process.returncode is not None else 1
        root.after(0, root.quit)

    threading.Thread(target=run_installer, daemon=True).start()

    root.update_idletasks()
    width = max(root.winfo_reqwidth(), 480)
    height = max(root.winfo_reqheight(), 420)
    root.geometry(f"{width}x{height}")
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
    root.geometry(f"{width}x{height}+{x}+{y}")

    root.mainloop()
    progress.stop()
    exit_code = exit_code_holder[0]

    if exit_code != 0:
        details = summarize_installer_failure(log_lines)
        messagebox.showerror(
            "Snappix",
            "Dependency installation failed.\n\n"
            f"{details}\n\n"
            "You can retry with:\n"
            "python3 install_dependencies.py",
        )

    root.destroy()
    return exit_code
