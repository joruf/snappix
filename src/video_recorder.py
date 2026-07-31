"""
ffmpeg-based video recording engine and export compositing for Snappix.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from src.py_compat import dataclass
from collections.abc import Callable
from pathlib import Path
from shutil import which

from PySide6.QtCore import QObject, QRect, Signal


class RecordingState:
    """
    Defines recording lifecycle states.
    """

    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"


def resolve_ffmpeg_path() -> str | None:
    """
    Resolves the ffmpeg executable path for the current machine.

    Prefers ``PATH``, then common Windows install locations (including winget
    package folders that may not yet be visible in a stale shell PATH).

    Returns:
        str | None: Absolute or bare ffmpeg path, or None when not found.
    """

    found = which("ffmpeg")
    if found:
        return found

    from src.paths import is_windows

    if not is_windows():
        return None

    candidates: list[Path] = []
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))

    winget_links = local_app / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    candidates.append(winget_links)

    winget_packages = local_app / "Microsoft" / "WinGet" / "Packages"
    if winget_packages.is_dir():
        for package_dir in winget_packages.glob("Gyan.FFmpeg*"):
            candidates.extend(package_dir.glob("**/ffmpeg.exe"))

    for base in (program_files, program_files_x86, Path(r"C:\ffmpeg")):
        candidates.append(base / "ffmpeg" / "bin" / "ffmpeg.exe")
        candidates.extend(base.glob("ffmpeg*/bin/ffmpeg.exe"))

    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def has_ffmpeg() -> bool:
    """
    Checks whether the ffmpeg binary is available.

    Returns:
        bool: True when ffmpeg exists on PATH or a known Windows install path.
    """

    return resolve_ffmpeg_path() is not None


def resolve_windows_dshow_audio_device() -> str | None:
    """
    Returns the first DirectShow audio capture device name, if any.

    ``audio=default`` is unreliable on Windows; callers should use a concrete
    device name from this helper or record without a microphone.

    Returns:
        str | None: Device name suitable for ``-i audio=NAME``, or None.
    """

    from src.paths import is_windows

    if not is_windows():
        return None

    ffmpeg_bin = resolve_ffmpeg_path()
    if not ffmpeg_bin:
        return None

    try:
        result = subprocess.run(
            [
                ffmpeg_bin,
                "-hide_banner",
                "-list_devices",
                "true",
                "-f",
                "dshow",
                "-i",
                "dummy",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            **_windows_subprocess_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None

    text = f"{result.stderr or ''}\n{result.stdout or ''}"
    in_audio_section = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if "directshow audio devices" in lower or "dshow audio devices" in lower:
            in_audio_section = True
            continue
        if in_audio_section and (
            "directshow video devices" in lower or "dshow video devices" in lower
        ):
            break
        if not in_audio_section:
            # Newer ffmpeg prints ``"Name" (audio)`` without a section header.
            if '(audio)' in lower and '"' in line:
                name = line.split('"', 2)
                if len(name) >= 2 and name[1].strip():
                    return name[1].strip()
            continue
        if line.startswith("Alternative name"):
            continue
        if '"' in line:
            name = line.split('"', 2)
            if len(name) >= 2 and name[1].strip():
                return name[1].strip()
    return None


def _windows_subprocess_kwargs() -> dict:
    """
    Returns Popen kwargs that hide the ffmpeg console window on Windows.

    Returns:
        dict: Extra keyword arguments for ``subprocess.Popen`` / ``run``.
    """

    from src.paths import is_windows

    if not is_windows():
        return {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if not creationflags:
        return {}
    return {"creationflags": creationflags}


def clamp_region_to_even_dimensions(rect: QRect) -> QRect:
    """
    Shrinks a capture region so width/height are even, as libx264/yuv420p requires.

    Args:
        rect: Requested capture region in absolute screen coordinates.

    Returns:
        QRect: Region with even width and height, same top-left corner.
    """

    width = rect.width() - (rect.width() % 2)
    height = rect.height() - (rect.height() % 2)
    return QRect(rect.x(), rect.y(), max(2, width), max(2, height))


def clamp_rect_to_virtual_desktop(rect: QRect) -> QRect:
    """
    Keeps one rectangle fully inside the combined virtual desktop bounds.

    Args:
        rect: Requested region in absolute screen coordinates.

    Returns:
        QRect: Clamped region with the same size as ``rect``.
    """

    try:
        from PySide6.QtGui import QGuiApplication
    except ModuleNotFoundError:
        return rect

    screens = QGuiApplication.screens()
    if not screens:
        return rect

    virtual = QRect()
    for screen in screens:
        virtual = virtual.united(screen.geometry())

    max_x = virtual.x() + max(0, virtual.width() - rect.width())
    max_y = virtual.y() + max(0, virtual.height() - rect.height())
    return QRect(
        max(virtual.x(), min(rect.x(), max_x)),
        max(virtual.y(), min(rect.y(), max_y)),
        rect.width(),
        rect.height(),
    )


def scale_rect_to_physical_pixels(rect: QRect, device_pixel_ratio: float) -> QRect:
    """
    Converts a logical (Qt device-independent) rect to physical pixel coordinates.

    ffmpeg's x11grab/gdigrab operate on the raw framebuffer regardless of any
    OS/desktop display scaling, while Qt reports screen and mouse geometry in
    scaled logical pixels whenever a display scale factor is active. Without
    this conversion, a scaled display makes the recording grab the wrong
    (often out-of-bounds) region, which shows up as a black or garbled video.

    Args:
        rect: Region in logical (Qt) coordinates.
        device_pixel_ratio: Scale factor of the screen the region is on.

    Returns:
        QRect: Equivalent region in physical pixel coordinates.
    """

    if abs(device_pixel_ratio - 1.0) < 0.001:
        return QRect(rect)
    return QRect(
        round(rect.x() * device_pixel_ratio),
        round(rect.y() * device_pixel_ratio),
        round(rect.width() * device_pixel_ratio),
        round(rect.height() * device_pixel_ratio),
    )


def _drain_and_print_stderr(stream) -> None:
    """
    Reads one process's stderr to completion and prints any output.

    Args:
        stream: Open stderr pipe of the ffmpeg subprocess.

    Returns:
        None
    """

    try:
        output = stream.read()
    except (OSError, ValueError):
        return
    text = output.decode("utf-8", errors="replace").strip() if output else ""
    if text:
        print(f"[snappix ffmpeg]\n{text}", file=sys.stderr)


def resolve_device_pixel_ratio_for_rect(rect: QRect) -> float:
    """
    Resolves the display scale factor for the screen a region is on.

    Args:
        rect: Region in logical (Qt) coordinates.

    Returns:
        float: Device pixel ratio of the containing screen, or 1.0 when
        no screen information is available.
    """

    try:
        from PySide6.QtGui import QGuiApplication
    except ModuleNotFoundError:
        return 1.0

    screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
    if screen is None:
        return 1.0
    return float(screen.devicePixelRatio())


def build_concat_command(list_path: Path, output_path: Path) -> list[str]:
    """
    Builds an ffmpeg concat command for one list of segment files.

    Args:
        list_path: Text file listing segment paths for the concat demuxer.
        output_path: Final merged MP4 output path.

    Returns:
        list[str]: ffmpeg argv-style command.
    """

    return [
        resolve_ffmpeg_path() or "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(output_path),
    ]


def build_record_command(
    rect: QRect,
    output_path: Path,
    *,
    record_microphone: bool,
    framerate: int = 30,
    display: str = ":0.0",
    windows_audio_device: str | None = None,
) -> list[str]:
    """
    Builds the ffmpeg command line for one screen recording.

    Uses ``x11grab`` on Linux and ``gdigrab`` on Windows.

    Args:
        rect: Capture region (already clamped to even dimensions).
        output_path: Destination MP4 file path.
        record_microphone: Whether to add a microphone audio input track.
        framerate: Capture framerate in frames per second.
        display: X11 display identifier for x11grab (Linux only).
        windows_audio_device: Concrete DirectShow audio device name on Windows.

    Returns:
        list[str]: Complete ffmpeg command line arguments (argv-style, no shell).
    """

    from src.paths import is_windows

    ffmpeg_bin = resolve_ffmpeg_path() or "ffmpeg"
    command = [ffmpeg_bin, "-y"]
    if is_windows():
        command += [
            "-f",
            "gdigrab",
            "-framerate",
            str(framerate),
            "-offset_x",
            str(rect.x()),
            "-offset_y",
            str(rect.y()),
            "-video_size",
            f"{rect.width()}x{rect.height()}",
            "-i",
            "desktop",
        ]
        if record_microphone and windows_audio_device:
            command += [
                "-f",
                "dshow",
                "-i",
                f"audio={windows_audio_device}",
                "-ac",
                "2",
                "-ar",
                "48000",
            ]
    else:
        command += [
            "-f",
            "x11grab",
            "-framerate",
            str(framerate),
            "-video_size",
            f"{rect.width()}x{rect.height()}",
            "-i",
            f"{display}+{rect.x()},{rect.y()}",
        ]
        if record_microphone:
            # Pulse default source; 48 kHz stereo AAC is a modest quality bump over
            # the previous 128k mono encode (still light enough for screen captures).
            command += [
                "-f",
                "pulse",
                "-i",
                "default",
                "-ac",
                "2",
                "-ar",
                "48000",
            ]

    command += [
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
    ]
    if record_microphone:
        command += ["-c:a", "aac", "-b:a", "192k"]
    command += ["-movflags", "+faststart", str(output_path)]
    return command


@dataclass(slots=True)
class OverlaySegment:
    """
    Defines one timed transparent PNG overlay for MP4 export compositing.

    Attributes:
        png_path: Path to the transparent annotation-layer PNG for this segment.
        start_s: Segment start time in seconds.
        end_s: Segment end time in seconds.
    """

    png_path: Path
    start_s: float
    end_s: float


def build_export_command(
    source_video: Path,
    overlay_segments: list[OverlaySegment],
    output_path: Path,
    *,
    include_audio: bool = True,
    report_progress: bool = False,
) -> list[str]:
    """
    Builds the ffmpeg command line that burns timed PNG overlays into a video.

    Args:
        source_video: Path to the raw recorded video.
        overlay_segments: Time-bounded transparent annotation-layer PNGs to composite.
        output_path: Destination MP4 file path.
        include_audio: When True, keep/re-encode the source audio track; when False,
            drop audio entirely (``-an``).
        report_progress: When True, add ``-progress pipe:1 -nostats`` so callers can
            stream encode progress from stdout (see :func:`run_ffmpeg_with_progress`).

    Returns:
        list[str]: Complete ffmpeg command line arguments (argv-style, no shell).
    """

    command = [resolve_ffmpeg_path() or "ffmpeg", "-y"]
    if report_progress:
        command += ["-progress", "pipe:1", "-nostats"]
    command += ["-i", str(source_video)]
    for segment in overlay_segments:
        command += ["-i", str(segment.png_path)]

    # Re-encode AAC on export so older 128k mono recordings also benefit from the
    # higher bitrate/sample-rate when the user keeps audio in the output.
    audio_encode_args = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]

    if not overlay_segments:
        command += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"]
        if include_audio:
            command += audio_encode_args
        else:
            command.append("-an")
        command.append(str(output_path))
        return command

    filter_parts = []
    current_label = "0:v"
    for index, segment in enumerate(overlay_segments):
        input_index = index + 1
        out_label = f"v{index}" if index < len(overlay_segments) - 1 else "vout"
        enable_expr = f"between(t,{segment.start_s},{segment.end_s})"
        filter_parts.append(
            f"[{current_label}][{input_index}:v]overlay=enable='{enable_expr}'[{out_label}]"
        )
        current_label = out_label

    filter_complex = ";".join(filter_parts)
    command += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
    ]
    if include_audio:
        command += ["-map", "0:a?"]
        command += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"]
        command += audio_encode_args
    else:
        command += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-an"]
    command.append(str(output_path))
    return command


def parse_ffmpeg_progress_ms(line: str) -> int | None:
    """
    Extracts the encoded-so-far position from one ``-progress`` output line.

    Args:
        line: A single ``key=value`` line from ffmpeg's progress stream.

    Returns:
        int | None: Encoded position in milliseconds, or None when the line
        carries no usable position.
    """

    key, separator, value = line.strip().partition("=")
    if not separator:
        return None
    key = key.strip()
    value = value.strip()
    if not value or value == "N/A":
        return None

    # ffmpeg reports out_time_us and out_time_ms both in MICROseconds -- the
    # "_ms" suffix is a long-standing upstream misnomer, so both scale alike.
    if key in ("out_time_us", "out_time_ms"):
        try:
            return max(0, int(value) // 1000)
        except ValueError:
            return None

    if key == "out_time":
        parts = value.split(":")
        if len(parts) != 3:
            return None
        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
        except ValueError:
            return None
        return max(0, int(((hours * 60 + minutes) * 60 + seconds) * 1000))

    return None


@dataclass(frozen=True, slots=True)
class FfmpegRunResult:
    """
    Describes the outcome of one monitored ffmpeg run.

    Attributes:
        returncode: Process exit code (-1 when the run never completed).
        stderr: Captured stderr text, used for error reporting.
        cancelled: True when the caller aborted the run.
        timed_out: True when the run exceeded its time budget and was killed.
    """

    returncode: int
    stderr: str
    cancelled: bool
    timed_out: bool

    @property
    def succeeded(self) -> bool:
        """
        Returns whether ffmpeg finished normally.

        Returns:
            bool: True on a clean exit that was neither cancelled nor timed out.
        """

        return self.returncode == 0 and not self.cancelled and not self.timed_out


def run_ffmpeg_with_progress(
    command: list[str],
    *,
    on_progress: Callable[[int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    poll_interval_s: float = 0.05,
    timeout_s: float | None = None,
) -> FfmpegRunResult:
    """
    Runs one ffmpeg command while streaming its progress and staying abortable.

    stdout and stderr are drained on background threads so a full pipe can never
    deadlock the run; the calling thread only polls, which lets a GUI caller keep
    its event loop alive inside ``on_progress``.

    Args:
        command: Full ffmpeg argv, built with ``report_progress=True``.
        on_progress: Called with the encoded position in milliseconds, roughly
            every ``poll_interval_s``. Runs on the calling thread.
        should_cancel: Polled between progress updates; returning True terminates
            ffmpeg and reports the run as cancelled.
        poll_interval_s: Delay between polls, in seconds.
        timeout_s: Optional wall-clock budget. Exceeding it kills ffmpeg.

    Returns:
        FfmpegRunResult: Exit code, captured stderr, and cancel/timeout flags.
    """

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            **_windows_subprocess_kwargs(),
        )
    except OSError as exc:
        return FfmpegRunResult(returncode=-1, stderr=str(exc), cancelled=False, timed_out=False)

    latest_ms = [0]
    stderr_chunks: list[str] = []

    def _drain_progress() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            position_ms = parse_ffmpeg_progress_ms(line)
            if position_ms is not None:
                latest_ms[0] = position_ms

    def _drain_stderr() -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            stderr_chunks.append(line)

    readers = [
        threading.Thread(target=_drain_progress, daemon=True, name="snappix-ffmpeg-progress"),
        threading.Thread(target=_drain_stderr, daemon=True, name="snappix-ffmpeg-stderr"),
    ]
    for reader in readers:
        reader.start()

    cancelled = False
    timed_out = False
    started_at = time.monotonic()

    while process.poll() is None:
        if should_cancel is not None and should_cancel():
            cancelled = True
            break
        if timeout_s is not None and (time.monotonic() - started_at) > timeout_s:
            timed_out = True
            break
        if on_progress is not None:
            on_progress(latest_ms[0])
        time.sleep(poll_interval_s)

    if cancelled or timed_out:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    else:
        process.wait()

    # Drain the readers before the final progress report. A short run can exit
    # before the polling loop ever iterates, so reporting first would publish a
    # stale position -- an export could finish showing less than 100%.
    for reader in readers:
        reader.join(timeout=2)

    if on_progress is not None and not cancelled and not timed_out:
        on_progress(latest_ms[0])

    return FfmpegRunResult(
        returncode=process.returncode if process.returncode is not None else -1,
        stderr="".join(stderr_chunks),
        cancelled=cancelled,
        timed_out=timed_out,
    )


class VideoRecorder(QObject):
    """
    Manages the lifecycle of one ffmpeg screen-recording subprocess.
    """

    state_changed = Signal(str)
    failed = Signal(str)
    finished = Signal(str)

    def __init__(self) -> None:
        """
        Initializes the recorder with no active process.
        """

        super().__init__()
        self._process: subprocess.Popen | None = None
        self._final_output_path: Path | None = None
        self._segments_dir: Path | None = None
        self._segment_paths: list[Path] = []
        self._record_microphone = False
        self._framerate = 30
        self._state = RecordingState.IDLE
        self._clamped_rect: QRect | None = None

    @property
    def state(self) -> str:
        """
        Returns the current recording state.

        Returns:
            str: One of the RecordingState constants.
        """

        return self._state

    @property
    def clamped_rect(self) -> QRect | None:
        """
        Returns the even-dimension-clamped region used for the active/last recording.

        Returns:
            QRect | None: Clamped capture region, or None before any recording starts.
        """

        return self._clamped_rect

    def start(
        self,
        rect: QRect,
        output_path: Path,
        *,
        record_microphone: bool,
        framerate: int = 30,
    ) -> bool:
        """
        Starts recording one screen region to a video file.

        Args:
            rect: Requested capture region in absolute screen coordinates.
            output_path: Destination MP4 file path.
            record_microphone: Whether to record microphone audio alongside video.
            framerate: Capture framerate in frames per second.

        Returns:
            bool: True when the ffmpeg process was launched successfully.
        """

        if not has_ffmpeg():
            self.failed.emit(
                "Video recording requires ffmpeg. Please install ffmpeg to enable this feature."
            )
            return False

        clamped_rect = clamp_region_to_even_dimensions(rect)
        self._clamped_rect = clamped_rect
        self._final_output_path = output_path
        self._segments_dir = output_path.parent / f".{output_path.stem}_segments"
        self._segments_dir.mkdir(parents=True, exist_ok=True)
        self._segment_paths = []
        self._record_microphone = record_microphone
        self._framerate = framerate
        if not self._launch_segment(clamped_rect):
            self._cleanup_segments_dir()
            self._final_output_path = None
            self._segments_dir = None
            self._clamped_rect = None
            return False

        self._state = RecordingState.RECORDING
        self.state_changed.emit(self._state)
        return True

    def _segment_path(self) -> Path:
        """
        Returns the path for the next recording segment file.

        Returns:
            Path: Segment MP4 path inside the temporary segments directory.
        """

        assert self._segments_dir is not None
        return self._segments_dir / f"part_{len(self._segment_paths):04d}.mp4"

    def _launch_segment(self, rect: QRect) -> bool:
        """
        Starts ffmpeg recording one screen region into a new segment file.

        On Windows, retries without microphone when DirectShow audio fails to
        open so region video capture still works.

        Args:
            rect: Even-dimension capture region.

        Returns:
            bool: True when ffmpeg launched successfully.
        """

        from src.paths import is_windows

        physical_rect = scale_rect_to_physical_pixels(
            rect, resolve_device_pixel_ratio_for_rect(rect)
        )

        want_mic = self._record_microphone
        windows_audio_device: str | None = None
        if is_windows() and want_mic:
            windows_audio_device = resolve_windows_dshow_audio_device()
            if windows_audio_device is None:
                want_mic = False

        attempts = [want_mic]
        if is_windows() and want_mic:
            attempts.append(False)

        last_error = ""
        for use_mic in attempts:
            segment_path = self._segment_path()
            if segment_path.exists():
                try:
                    segment_path.unlink()
                except OSError:
                    pass
            command = build_record_command(
                physical_rect,
                segment_path,
                record_microphone=use_mic,
                framerate=self._framerate,
                display=os.environ.get("DISPLAY") or ":0.0",
                windows_audio_device=windows_audio_device if use_mic else None,
            )
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    **_windows_subprocess_kwargs(),
                )
            except OSError as exc:
                last_error = f"Could not start ffmpeg: {exc}"
                continue

            # Mic/dshow open can take >0.35s before failing; wait longer on Windows.
            health_s = 1.2 if (use_mic and is_windows()) else 0.35
            time.sleep(health_s)
            if process.poll() is None:
                self._process = process
                self._record_microphone = use_mic
                self._segment_paths.append(segment_path)
                return True

            exit_code = process.returncode
            stderr_text = ""
            if process.stderr is not None:
                try:
                    stderr_text = process.stderr.read().decode("utf-8", errors="replace")
                except OSError:
                    stderr_text = ""
            last_error = (
                stderr_text.strip().splitlines()[-1]
                if stderr_text.strip()
                else f"ffmpeg exited immediately (code {exit_code})."
            )
            if use_mic and is_windows():
                continue
            break

        self.failed.emit(last_error or "Could not start ffmpeg.")
        return False

    def _terminate_current_process_blocking(self) -> None:
        """
        Stops the active ffmpeg segment and waits for it to finalize the file.

        On Windows, ``SIGINT`` is unsupported for child processes, so ffmpeg is
        asked to quit by writing ``q`` to stdin. stderr is drained in the
        background so a full pipe cannot deadlock the wait.

        Returns:
            None
        """

        from src.paths import is_windows

        if self._process is None:
            return

        process = self._process
        if (
            not is_windows()
            and self._state == RecordingState.PAUSED
            and hasattr(signal, "SIGCONT")
        ):
            try:
                os.kill(process.pid, signal.SIGCONT)
            except (ProcessLookupError, AttributeError, OSError):
                pass

        # Prevent deadlock: ffmpeg logs to stderr and can block when the pipe fills.
        # Printed (not just drained) so recording problems are visible in the
        # terminal instead of being silently swallowed.
        if process.stderr is not None:
            threading.Thread(
                target=lambda: _drain_and_print_stderr(process.stderr),
                daemon=True,
                name="snappix-ffmpeg-stderr-drain",
            ).start()

        # Graceful quit — required on Windows; also works on Linux.
        try:
            if process.stdin is not None:
                process.stdin.write(b"q\n")
                process.stdin.flush()
                process.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass

        if not is_windows():
            try:
                if hasattr(signal, "SIGINT"):
                    process.send_signal(signal.SIGINT)
                else:
                    process.terminate()
            except (ProcessLookupError, AttributeError, OSError, ValueError):
                try:
                    process.terminate()
                except ProcessLookupError:
                    self._process = None
                    return

        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        self._process = None

    def _cleanup_segments_dir(self) -> None:
        """
        Deletes temporary segment files created for one recording session.

        Returns:
            None
        """

        if self._segments_dir is None or not self._segments_dir.exists():
            return

        def _safe_unlink(path: Path) -> None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # Windows may keep a short lock on just-written segment files.
                pass

        for segment_path in self._segment_paths:
            if segment_path.exists():
                _safe_unlink(segment_path)
        for leftover in self._segments_dir.glob("*"):
            _safe_unlink(leftover)
        try:
            self._segments_dir.rmdir()
        except OSError:
            pass

    def _assemble_segments(self, output_path: Path) -> None:
        """
        Merges recorded segment files into the final output MP4.

        Args:
            output_path: Destination recording path.

        Returns:
            None
        """

        segments = [
            segment_path
            for segment_path in self._segment_paths
            if segment_path.is_file() and segment_path.stat().st_size > 0
        ]
        if not segments:
            raise RuntimeError("Recording produced no video data.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if len(segments) == 1:
            segments[0].replace(output_path)
            return

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".txt",
            delete=False,
        ) as list_handle:
            for segment_path in segments:
                list_handle.write(f"file '{segment_path.as_posix()}'\n")
            list_path = Path(list_handle.name)

        try:
            result = subprocess.run(
                build_concat_command(list_path, output_path),
                capture_output=True,
                text=True,
                check=False,
                **_windows_subprocess_kwargs(),
            )
        finally:
            list_path.unlink(missing_ok=True)

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(detail or "Could not merge recording segments.")

    def relocate(self, rect: QRect) -> bool:
        """
        Moves the active capture region while keeping its recorded size.

        Finalizes the current ffmpeg segment and starts a new one at the new
        screen coordinates.

        Args:
            rect: Requested top-left position in absolute screen coordinates.

        Returns:
            bool: True when the recorder switched to the new region.
        """

        if self._state == RecordingState.IDLE or self._clamped_rect is None:
            return False

        preserved_size = self._clamped_rect.size()
        clamped_rect = clamp_region_to_even_dimensions(
            clamp_rect_to_virtual_desktop(
                QRect(rect.x(), rect.y(), preserved_size.width(), preserved_size.height())
            )
        )
        if clamped_rect == self._clamped_rect and self._process is not None:
            return True

        was_paused = self._state == RecordingState.PAUSED
        self._terminate_current_process_blocking()
        self._clamped_rect = clamped_rect
        if not self._launch_segment(clamped_rect):
            self.failed.emit("Could not move the recording region.")
            return False

        self._state = RecordingState.RECORDING
        self.state_changed.emit(self._state)
        if was_paused:
            self.pause()
        return True

    def pause(self) -> None:
        """
        Pauses the active recording.

        On Linux this suspends ffmpeg with SIGSTOP. On Windows (no SIGSTOP)
        the current segment is finalized and a new one starts on resume.

        Returns:
            None
        """

        from src.paths import is_windows

        if self._state != RecordingState.RECORDING:
            return
        if is_windows():
            if self._process is None:
                return
            self._terminate_current_process_blocking()
            self._state = RecordingState.PAUSED
            self.state_changed.emit(self._state)
            return
        if self._process is None:
            return
        try:
            os.kill(self._process.pid, signal.SIGSTOP)
        except (ProcessLookupError, AttributeError, OSError):
            return
        self._state = RecordingState.PAUSED
        self.state_changed.emit(self._state)

    def resume(self) -> None:
        """
        Resumes a paused recording.

        Returns:
            None
        """

        from src.paths import is_windows

        if self._state != RecordingState.PAUSED:
            return
        if is_windows():
            if self._clamped_rect is None:
                return
            if not self._launch_segment(self._clamped_rect):
                self.failed.emit("Could not resume recording.")
                return
            self._state = RecordingState.RECORDING
            self.state_changed.emit(self._state)
            return
        if self._process is None:
            return
        try:
            os.kill(self._process.pid, signal.SIGCONT)
        except (ProcessLookupError, AttributeError, OSError):
            return
        self._state = RecordingState.RECORDING
        self.state_changed.emit(self._state)

    def stop(self) -> None:
        """
        Stops the active recording and finalizes the output file.

        Emits ``finished`` with the output path once segments are merged, or
        ``failed`` if the recording could not be finalized.

        Returns:
            None
        """

        if self._process is None and not self._segment_paths:
            return

        output_path = self._final_output_path
        self._terminate_current_process_blocking()
        self._state = RecordingState.IDLE
        self.state_changed.emit(self._state)

        if output_path is None:
            return

        try:
            self._assemble_segments(output_path)
        except RuntimeError as exc:
            self.failed.emit(str(exc))
            self._cleanup_segments_dir()
            self._final_output_path = None
            self._segments_dir = None
            self._segment_paths = []
            self._clamped_rect = None
            return

        self._cleanup_segments_dir()
        self._final_output_path = None
        self._segments_dir = None
        self._segment_paths = []
        self.finished.emit(str(output_path))
