"""
Tkinter progress dialog for first-time dependency installation.
"""

from __future__ import annotations

import math
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

SPLASH_BG = "#1a1f2a"
SPLASH_BG_RGB = (26, 31, 42)
SPLASH_PEN_BODY = "#e8c547"
ANIM_CANVAS_WIDTH = 420
ANIM_CANVAS_HEIGHT = 130
ANIM_TAG = "anim"
# Arc length advanced per frame (~30fps) — intentionally fast.
PEN_SPEED_PX_PER_FRAME = 14.0
PEN_SAMPLE_STEP_PX = 3.0
# Older ink fades out after this much travel behind the tip.
PEN_FADE_LENGTH_PX = 520.0
# Full hue cycle length — slow rainbow while drawing.
PEN_HUE_CYCLE_PX = 1800.0


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
    if "installing windows packages via winget" in lowered or "winget install" in lowered:
        return "Installing Windows tools via winget…"
    if "installing uv" in lowered or "uv toolchain" in lowered:
        return "Installing uv toolchain…"
    if "downloading" in lowered and "uv" in lowered:
        return "Downloading uv toolchain…"
    if "ensuring python" in lowered or "python 3.12 runtime" in lowered:
        return "Downloading Python 3.12 runtime…"
    if "requesting administrator rights via pkexec" in lowered:
        return "Waiting for administrator password dialog…"
    if "required system packages are present" in lowered or "required tools are present" in lowered:
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


def hsv_to_hex(hue: float, saturation: float = 0.85, value: float = 1.0) -> str:
    """
    Converts HSV color components to a Tk hex color string.

    Args:
        hue: Hue in ``[0, 1)``.
        saturation: Saturation in ``[0, 1]``.
        value: Value/brightness in ``[0, 1]``.

    Returns:
        str: ``#RRGGBB`` color.
    """

    hue_wrapped = hue - math.floor(hue)
    sat = max(0.0, min(float(saturation), 1.0))
    val = max(0.0, min(float(value), 1.0))
    sector = hue_wrapped * 6.0
    chroma = val * sat
    intermediate = chroma * (1.0 - abs(sector % 2.0 - 1.0))
    match = math.floor(sector) % 6
    if match == 0:
        red, green, blue = chroma, intermediate, 0.0
    elif match == 1:
        red, green, blue = intermediate, chroma, 0.0
    elif match == 2:
        red, green, blue = 0.0, chroma, intermediate
    elif match == 3:
        red, green, blue = 0.0, intermediate, chroma
    elif match == 4:
        red, green, blue = intermediate, 0.0, chroma
    else:
        red, green, blue = chroma, 0.0, intermediate
    lift = val - chroma
    return (
        f"#{int(round((red + lift) * 255)):02x}"
        f"{int(round((green + lift) * 255)):02x}"
        f"{int(round((blue + lift) * 255)):02x}"
    )


def ink_hue_at(distance: float, *, cycle_px: float = PEN_HUE_CYCLE_PX) -> float:
    """
    Returns the slowly advancing ink hue for a travel distance.

    Args:
        distance: Pen travel distance in pixels.
        cycle_px: Distance that completes one full rainbow cycle.

    Returns:
        float: Hue in ``[0, 1)``.
    """

    period = max(1.0, float(cycle_px))
    return (max(0.0, float(distance)) / period) % 1.0


def ink_fade_alpha(
    sample_distance: float,
    tip_distance: float,
    *,
    fade_length: float = PEN_FADE_LENGTH_PX,
) -> float:
    """
    Returns opacity for ink at ``sample_distance`` given the current tip.

    Args:
        sample_distance: Arc length where the ink sample was drawn.
        tip_distance: Current pen tip travel distance.
        fade_length: How far behind the tip ink remains visible.

    Returns:
        float: Opacity in ``[0, 1]`` (0 = fully faded away).
    """

    age = max(0.0, float(tip_distance) - float(sample_distance))
    length = max(1.0, float(fade_length))
    if age >= length:
        return 0.0
    # Ease out so the tail softens before disappearing.
    remaining = 1.0 - (age / length)
    return remaining * remaining


def blend_hex_toward_background(color_hex: str, alpha: float) -> str:
    """
    Blends a hex color toward the splash background for fade-out.

    Args:
        color_hex: Source ``#RRGGBB`` color.
        alpha: Opacity in ``[0, 1]`` (1 keeps the ink color).

    Returns:
        str: Blended ``#RRGGBB`` color.
    """

    clamped = max(0.0, min(float(alpha), 1.0))
    cleaned = color_hex.lstrip("#")
    if len(cleaned) != 6:
        return color_hex
    red = int(cleaned[0:2], 16)
    green = int(cleaned[2:4], 16)
    blue = int(cleaned[4:6], 16)
    bg_r, bg_g, bg_b = SPLASH_BG_RGB
    out_r = int(round(red * clamped + bg_r * (1.0 - clamped)))
    out_g = int(round(green * clamped + bg_g * (1.0 - clamped)))
    out_b = int(round(blue * clamped + bg_b * (1.0 - clamped)))
    return f"#{out_r:02x}{out_g:02x}{out_b:02x}"


def ink_color_at(
    sample_distance: float,
    tip_distance: float,
    *,
    fade_length: float = PEN_FADE_LENGTH_PX,
    cycle_px: float = PEN_HUE_CYCLE_PX,
) -> str | None:
    """
    Resolves the faded rainbow ink color for one sample along the trail.

    Args:
        sample_distance: Arc length of the sample.
        tip_distance: Current tip travel distance.
        fade_length: Visible trail length behind the tip.
        cycle_px: Rainbow cycle length.

    Returns:
        str | None: Hex color, or None when the sample has fully faded.
    """

    alpha = ink_fade_alpha(sample_distance, tip_distance, fade_length=fade_length)
    if alpha <= 0.02:
        return None
    vivid = hsv_to_hex(ink_hue_at(sample_distance, cycle_px=cycle_px))
    return blend_hex_toward_background(vivid, alpha)


def pen_path_at(
    distance: float,
    *,
    width: float = ANIM_CANVAS_WIDTH,
    height: float = ANIM_CANVAS_HEIGHT,
) -> tuple[float, float]:
    """
    Maps arc length along an unbounded doodle into canvas coordinates.

    The path keeps meandering forever: longer load time yields a longer ink trail.

    Args:
        distance: Arc length traveled by the pen tip in pixels.
        width: Canvas width.
        height: Canvas height.

    Returns:
        tuple[float, float]: Point on the doodle path.
    """

    margin_x = 28.0
    margin_y = 22.0
    usable_w = max(width - 2.0 * margin_x, 1.0)
    usable_h = max(height - 2.0 * margin_y, 1.0)
    # Bounce horizontally so the stroke stays on-canvas while growing.
    period = usable_w * 2.0
    sweep = distance % period
    if sweep > usable_w:
        x = margin_x + (period - sweep)
    else:
        x = margin_x + sweep
    # Layered waves give a quick hand-drawn scribble feel.
    y = (
        margin_y
        + usable_h * 0.52
        + math.sin(distance * 0.065) * usable_h * 0.32
        + math.sin(distance * 0.019 + 1.2) * usable_h * 0.14
        + math.sin(distance * 0.14) * 5.0
    )
    return (x, y)


def pen_trail_samples(
    tip_distance: float,
    *,
    width: float = ANIM_CANVAS_WIDTH,
    height: float = ANIM_CANVAS_HEIGHT,
    step: float = PEN_SAMPLE_STEP_PX,
    fade_length: float = PEN_FADE_LENGTH_PX,
) -> list[tuple[float, float, float]]:
    """
    Samples the visible (not yet faded) pen trail behind the tip.

    Args:
        tip_distance: Current pen tip travel distance.
        width: Canvas width.
        height: Canvas height.
        step: Sampling step along the path.
        fade_length: How far behind the tip ink remains.

    Returns:
        list[tuple[float, float, float]]: ``(x, y, sample_distance)`` samples.
    """

    tip = max(0.0, float(tip_distance))
    if tip <= 0.0:
        return []
    sample_step = max(1.0, float(step))
    start = max(0.0, tip - max(1.0, float(fade_length)))
    samples: list[tuple[float, float, float]] = []
    sample = start
    while sample <= tip:
        x, y = pen_path_at(sample, width=width, height=height)
        samples.append((x, y, sample))
        sample += sample_step
    tip_point = pen_path_at(tip, width=width, height=height)
    if not samples or samples[-1][2] < tip:
        samples.append((tip_point[0], tip_point[1], tip))
    return samples


def pen_trail_points(
    distance: float,
    *,
    width: float = ANIM_CANVAS_WIDTH,
    height: float = ANIM_CANVAS_HEIGHT,
    step: float = PEN_SAMPLE_STEP_PX,
    fade_length: float = PEN_FADE_LENGTH_PX,
) -> list[tuple[float, float]]:
    """
    Samples visible trail coordinates up to ``distance`` (faded tail omitted).

    Args:
        distance: How far the pen has traveled in pixels.
        width: Canvas width.
        height: Canvas height.
        step: Sampling step along the path.
        fade_length: Visible trail length behind the tip.

    Returns:
        list[tuple[float, float]]: Polyline points for ink still visible.
    """

    return [
        (x, y)
        for x, y, _sample in pen_trail_samples(
            distance,
            width=width,
            height=height,
            step=step,
            fade_length=fade_length,
        )
    ]


def pen_tip_angle(
    distance: float,
    *,
    width: float = ANIM_CANVAS_WIDTH,
    height: float = ANIM_CANVAS_HEIGHT,
    lookback: float = 8.0,
) -> float:
    """
    Returns the pen orientation in radians along the doodle tangent.

    Args:
        distance: Current pen travel distance.
        width: Canvas width.
        height: Canvas height.
        lookback: Distance behind the tip used for the tangent.

    Returns:
        float: Angle in radians (canvas y grows downward).
    """

    travel = max(0.0, float(distance))
    tip = pen_path_at(travel, width=width, height=height)
    behind = pen_path_at(max(0.0, travel - lookback), width=width, height=height)
    return math.atan2(tip[1] - behind[1], tip[0] - behind[0])


class SplashPenAnimation:
    """
    Draws with a visible pen tip; ink grows while loading, shifts hue, and fades.
    """

    def __init__(
        self,
        canvas: tk.Canvas,
        *,
        interval_ms: int = 33,
        speed_px: float = PEN_SPEED_PX_PER_FRAME,
    ) -> None:
        """
        Binds the animator to one canvas.

        Args:
            canvas: Target drawing surface.
            interval_ms: Frame delay in milliseconds.
            speed_px: Arc length advanced each frame.
        """

        self._canvas = canvas
        self._interval_ms = max(16, int(interval_ms))
        self._speed_px = max(1.0, float(speed_px))
        self._after_id: str | None = None
        self._running = False
        self._distance = 0.0

    @property
    def is_running(self) -> bool:
        """
        Returns whether the animation loop is active.

        Returns:
            bool: True while frames are scheduled.
        """

        return self._running

    @property
    def distance(self) -> float:
        """
        Returns how far the pen has traveled in pixels.

        Returns:
            float: Ink arc length.
        """

        return self._distance

    def start(self) -> None:
        """
        Starts the pen animation if it is not already running.

        Returns:
            None
        """

        if self._running:
            return
        self._running = True
        self._distance = 0.0
        self._tick()

    def stop(self) -> None:
        """
        Stops the animation loop and cancels any pending frame.

        Returns:
            None
        """

        self._running = False
        if self._after_id is not None:
            try:
                self._canvas.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _tick(self) -> None:
        """
        Advances the pen, redraws ink, and schedules the next frame.

        Returns:
            None
        """

        if not self._running:
            return
        self._distance += self._speed_px
        try:
            self._draw_frame()
        except tk.TclError:
            self._running = False
            self._after_id = None
            return
        self._after_id = self._canvas.after(self._interval_ms, self._tick)

    def _draw_frame(self) -> None:
        """
        Redraws the fading rainbow ink trail and pen tip.

        Returns:
            None
        """

        canvas = self._canvas
        canvas.delete(ANIM_TAG)
        width = float(canvas.winfo_width() or ANIM_CANVAS_WIDTH)
        height = float(canvas.winfo_height() or ANIM_CANVAS_HEIGHT)
        if width < 2:
            width = float(ANIM_CANVAS_WIDTH)
        if height < 2:
            height = float(ANIM_CANVAS_HEIGHT)

        samples = pen_trail_samples(self._distance, width=width, height=height)
        # Short colored segments: hue shifts along the stroke, older ink fades out.
        for index in range(len(samples) - 1):
            x0, y0, d0 = samples[index]
            x1, y1, d1 = samples[index + 1]
            mid = (d0 + d1) * 0.5
            color = ink_color_at(mid, self._distance)
            if color is None:
                continue
            canvas.create_line(
                x0,
                y0,
                x1,
                y1,
                fill=color,
                width=2.8,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
                tags=ANIM_TAG,
            )

        if samples:
            tip_x, tip_y, _tip_d = samples[-1]
        else:
            tip_x, tip_y = pen_path_at(self._distance, width=width, height=height)
        angle = pen_tip_angle(self._distance, width=width, height=height)
        ink_now = hsv_to_hex(ink_hue_at(self._distance))
        self._draw_pen(tip_x, tip_y, angle, ink_color=ink_now)

    def _draw_pen(
        self,
        x: float,
        y: float,
        angle: float,
        *,
        ink_color: str,
    ) -> None:
        """
        Draws a small pen/stylus at the active tip.

        Args:
            x: Tip x coordinate.
            y: Tip y coordinate.
            angle: Travel direction in radians.
            ink_color: Current ink hue used for the nib accent.

        Returns:
            None
        """

        canvas = self._canvas
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        # Local pen geometry: tip at origin, body extends backward.
        local_body = [
            (0.0, 0.0),
            (-6.0, -3.5),
            (-22.0, -3.0),
            (-26.0, 0.0),
            (-22.0, 3.0),
            (-6.0, 3.5),
        ]
        world: list[float] = []
        for lx, ly in local_body:
            wx = x + lx * cos_a - ly * sin_a
            wy = y + lx * sin_a + ly * cos_a
            world.extend((wx, wy))
        canvas.create_polygon(
            *world,
            fill=SPLASH_PEN_BODY,
            outline="#8a6d1a",
            width=1,
            tags=ANIM_TAG,
        )
        canvas.create_oval(
            x - 2.4,
            y - 2.4,
            x + 2.4,
            y + 2.4,
            fill=ink_color,
            outline="",
            tags=ANIM_TAG,
        )
        canvas.create_oval(
            x - 7.0,
            y - 7.0,
            x + 7.0,
            y + 7.0,
            outline=ink_color,
            width=1,
            tags=ANIM_TAG,
        )


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
    root.configure(bg=SPLASH_BG)

    frame = tk.Frame(root, bg=SPLASH_BG, padx=36, pady=28)
    frame.grid(row=0, column=0, sticky="nsew")

    logo = _load_splash_logo(root)
    if logo is not None:
        logo_label = tk.Label(frame, image=logo, bg=SPLASH_BG, borderwidth=0)
        logo_label.grid(row=0, column=0, pady=(4, 10))
    else:
        title = tk.Label(
            frame,
            text="Snappix",
            font=("Segoe UI", 28, "bold"),
            fg="#f4f8ff",
            bg=SPLASH_BG,
        )
        title.grid(row=0, column=0, pady=(8, 10))

    anim_canvas = tk.Canvas(
        frame,
        width=ANIM_CANVAS_WIDTH,
        height=ANIM_CANVAS_HEIGHT,
        bg=SPLASH_BG,
        highlightthickness=0,
        borderwidth=0,
    )
    anim_canvas.grid(row=1, column=0, pady=(0, 12))
    pen_animation = SplashPenAnimation(anim_canvas)

    brand = tk.Label(
        frame,
        text="Snappix",
        font=("Segoe UI", 18, "bold"),
        fg="#f4f8ff",
        bg=SPLASH_BG,
    )
    brand.grid(row=2, column=0, pady=(0, 6))

    subtitle = tk.Label(
        frame,
        text="Checking installation…",
        font=("Segoe UI", 10),
        fg="#9aa6b8",
        bg=SPLASH_BG,
    )
    subtitle.grid(row=3, column=0, pady=(0, 16))

    status_var = tk.StringVar(value="Preparing to verify dependencies…")
    status_label = tk.Label(
        frame,
        textvariable=status_var,
        font=("Segoe UI", 10),
        fg="#d7dee8",
        bg=SPLASH_BG,
        wraplength=420,
        justify="center",
    )
    status_label.grid(row=4, column=0, pady=(0, 14))

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
    progress.grid(row=5, column=0, pady=(0, 14))
    progress.start(14)

    hint = tk.Label(
        frame,
        text=(
            "If an administrator dialog appears, confirm it to install system packages.\n"
            "Python packages are installed into a local .venv."
        ),
        font=("Segoe UI", 9),
        fg="#7f8b9c",
        bg=SPLASH_BG,
        wraplength=420,
        justify="center",
    )
    hint.grid(row=6, column=0)

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
    height = max(root.winfo_reqheight(), 520)
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

    pen_animation.start()
    root.mainloop()
    pen_animation.stop()
    progress.stop()
    exit_code = exit_code_holder[0]

    if exit_code != 0:
        details = summarize_installer_failure(log_lines)
        messagebox.showerror(
            "Snappix",
            "Dependency installation failed.\n\n"
            f"{details}\n\n"
            "You can retry with:\n"
            "Snappix.bat   (Windows)\n"
            "./snappix.sh  (Linux)\n"
            "or: python install_dependencies.py",
        )

    root.destroy()
    return exit_code
