"""
ffmpeg-based video recording engine and export compositing for Snappix.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
from dataclasses import dataclass
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


def has_ffmpeg() -> bool:
    """
    Checks whether the ffmpeg binary is available.

    Returns:
        bool: True when ffmpeg exists on PATH.
    """

    return which("ffmpeg") is not None


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
        "ffmpeg",
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
) -> list[str]:
    """
    Builds the ffmpeg command line for one X11 screen recording.

    Args:
        rect: Capture region (already clamped to even dimensions).
        output_path: Destination MP4 file path.
        record_microphone: Whether to add a microphone audio input track.
        framerate: Capture framerate in frames per second.
        display: X11 display identifier for x11grab.

    Returns:
        list[str]: Complete ffmpeg command line arguments (argv-style, no shell).
    """

    command = [
        "ffmpeg",
        "-y",
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
) -> list[str]:
    """
    Builds the ffmpeg command line that burns timed PNG overlays into a video.

    Args:
        source_video: Path to the raw recorded video.
        overlay_segments: Time-bounded transparent annotation-layer PNGs to composite.
        output_path: Destination MP4 file path.
        include_audio: When True, keep/re-encode the source audio track; when False,
            drop audio entirely (``-an``).

    Returns:
        list[str]: Complete ffmpeg command line arguments (argv-style, no shell).
    """

    command = ["ffmpeg", "-y", "-i", str(source_video)]
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

        Args:
            rect: Even-dimension capture region.

        Returns:
            bool: True when ffmpeg launched successfully.
        """

        segment_path = self._segment_path()
        command = build_record_command(
            rect,
            segment_path,
            record_microphone=self._record_microphone,
            framerate=self._framerate,
        )
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            self.failed.emit(f"Could not start ffmpeg: {exc}")
            return False

        self._segment_paths.append(segment_path)
        return True

    def _terminate_current_process_blocking(self) -> None:
        """
        Stops the active ffmpeg segment and waits for it to finalize the file.

        Returns:
            None
        """

        if self._process is None:
            return

        process = self._process
        if self._state == RecordingState.PAUSED:
            try:
                os.kill(process.pid, signal.SIGCONT)
            except ProcessLookupError:
                pass

        try:
            process.send_signal(signal.SIGINT)
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
        for segment_path in self._segment_paths:
            if segment_path.exists():
                segment_path.unlink(missing_ok=True)
        for leftover in self._segments_dir.glob("*"):
            leftover.unlink(missing_ok=True)
        self._segments_dir.rmdir()

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
        Pauses the active recording by suspending the ffmpeg process.

        Returns:
            None
        """

        if self._process is None or self._state != RecordingState.RECORDING:
            return
        try:
            os.kill(self._process.pid, signal.SIGSTOP)
        except ProcessLookupError:
            return
        self._state = RecordingState.PAUSED
        self.state_changed.emit(self._state)

    def resume(self) -> None:
        """
        Resumes a paused recording.

        Returns:
            None
        """

        if self._process is None or self._state != RecordingState.PAUSED:
            return
        try:
            os.kill(self._process.pid, signal.SIGCONT)
        except ProcessLookupError:
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
