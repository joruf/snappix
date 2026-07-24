"""
ffmpeg-based video recording engine and export compositing for Snappix.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from PySide6.QtCore import QObject, QRect, QTimer, Signal


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
        self._output_path: Path | None = None
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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = build_record_command(
            clamped_rect,
            output_path,
            record_microphone=record_microphone,
            framerate=framerate,
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

        self._output_path = output_path
        self._state = RecordingState.RECORDING
        self.state_changed.emit(self._state)
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

        Emits ``finished`` with the output path once ffmpeg exits cleanly, or
        ``failed`` if the process could not be found/terminated.

        Returns:
            None
        """

        if self._process is None:
            return

        process = self._process
        output_path = self._output_path

        if self._state == RecordingState.PAUSED:
            # A stopped process holds signals pending until continued, so resume
            # first or the following SIGINT would only be delivered on wake-up.
            try:
                os.kill(process.pid, signal.SIGCONT)
            except ProcessLookupError:
                pass

        try:
            process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            pass

        self._process = None
        self._output_path = None
        self._state = RecordingState.IDLE
        self.state_changed.emit(self._state)

        self._poll_for_exit(process, output_path, elapsed_ms=0)

    def _poll_for_exit(
        self,
        process: subprocess.Popen,
        output_path: Path | None,
        *,
        elapsed_ms: int,
    ) -> None:
        """
        Polls one ffmpeg process for exit without blocking the Qt event loop.

        Args:
            process: ffmpeg subprocess to await.
            output_path: Output file path to report once the process exits.
            elapsed_ms: Milliseconds waited so far, used to escalate to
                terminate()/kill() if ffmpeg does not exit after SIGINT.

        Returns:
            None
        """

        return_code = process.poll()
        if return_code is None:
            if elapsed_ms >= 10_000:
                process.kill()
            elif elapsed_ms >= 5_000:
                process.terminate()
            QTimer.singleShot(
                100,
                lambda: self._poll_for_exit(process, output_path, elapsed_ms=elapsed_ms + 100),
            )
            return

        if output_path is not None:
            self.finished.emit(str(output_path))
