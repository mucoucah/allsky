"""Pick an ffmpeg encoder. NVENC when the Windows driver exposes it, else libx264."""
from __future__ import annotations


def parse_encoders(text: str) -> set[str]:
    found: set[str] = set()
    for line in text.splitlines():
        for name in ("h264_nvenc", "hevc_nvenc", "libx264"):
            if name in line:
                found.add(name)
    return found


def encoder_args(preference: str, available: set[str]) -> list[str]:
    """Return ffmpeg arguments that select one video encoder."""
    choice = preference
    if choice == "auto":
        if "h264_nvenc" in available:
            choice = "h264_nvenc"
        elif "hevc_nvenc" in available:
            choice = "hevc_nvenc"
        else:
            choice = "libx264"
    if choice == "h264_nvenc" and "h264_nvenc" in available:
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "28"]
    if choice == "hevc_nvenc" and "hevc_nvenc" in available:
        return ["-c:v", "hevc_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "28"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]


def timelapse_command(list_file: str, dest: str, video_args: list[str]) -> list[str]:
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", list_file,
        "-r", "24",
        *video_args,
        "-pix_fmt", "yuv420p",
        dest,
    ]
