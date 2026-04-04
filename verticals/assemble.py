"""ffmpeg video assembly — frames + voiceover + music + captions."""

import os
import re
import sys
from pathlib import Path


def _ass_no_spaces(ass_path: Path, job_id: str) -> Path:
    """Return a copy of the ASS file at a path guaranteed to have no spaces.

    FFmpeg's filter parser cannot handle spaces (or Windows colon paths) in
    the ass= filter value, even with escaping. Copying to a short temp path
    avoids the issue entirely.
    """
    import shutil

    if sys.platform != "win32":
        return ass_path

    # Try candidates in order until we find a writable dir with no spaces
    candidates = [
        Path("C:/Windows/Temp"),
        Path(os.environ.get("SYSTEMDRIVE", "C:") + "/tmp"),
        Path("D:/tmp"),
    ]
    for d in candidates:
        if " " in str(d):
            continue
        try:
            d.mkdir(parents=True, exist_ok=True)
            dest = d / f"captions_{job_id}.ass"
            shutil.copy2(ass_path, dest)
            return dest
        except Exception:
            continue

    # Fallback: return original path (may fail if it has spaces)
    return ass_path

from .broll import animate_frame
from .config import MEDIA_DIR, run_cmd
from .log import log


def get_audio_duration(path: Path) -> float:
    """Get duration of an audio file in seconds."""
    r = run_cmd(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture=True,
    )
    return float(r.stdout.strip())


def assemble_video(
    frames: list[Path],
    voiceover: Path,
    out_dir: Path,
    job_id: str,
    lang: str = "en",
    ass_path: str | None = None,
    music_path: str | None = None,
    duck_filter: str | None = None,
) -> Path:
    """Assemble final video from frames, voiceover, captions, and music."""
    log("Assembling video...")
    duration = get_audio_duration(voiceover)

    # Cut every 2 seconds — cycle through available frames to fill the full duration
    per_clip = 2.0
    n_clips = max(len(frames), round(duration / per_clip))
    clip_sequence = [frames[i % len(frames)] for i in range(n_clips)]
    clip_dur = duration / n_clips  # actual duration per clip
    effects = ["zoom_in", "pan_right", "zoom_out"]

    # Animate each clip with alternating Ken Burns effects
    animated = []
    for i, frame in enumerate(clip_sequence):
        anim = out_dir / f"anim_{i}.mp4"
        animate_frame(frame, anim, clip_dur + 0.1, effects[i % len(effects)])
        animated.append(anim)

    # Concat animated segments (escape single quotes for ffmpeg concat demuxer)
    concat_file = out_dir / "concat.txt"
    def _esc(p):
        return str(p).replace("'", "'\\''" )
    concat_file.write_text("\n".join(f"file '{_esc(p)}'" for p in animated))

    merged_video = out_dir / "merged_video.mp4"
    run_cmd([
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        str(merged_video), "-y", "-loglevel", "quiet",
    ])

    # Build the final ffmpeg command with optional captions + music
    out_path = MEDIA_DIR / f"verticals_{job_id}_{lang}.mp4"

    # Determine video filter (captions via ASS)
    # On Windows, FFmpeg's filter parser chokes on any path containing `:` (drive
    # letter) even when escaped. Work-around: copy the ASS to a temp dir, then
    # run FFmpeg with cwd=that dir and reference only the bare filename in the
    # filter — no colon, no slashes, no spaces, nothing to escape.
    vf_parts = []
    ffmpeg_cwd = None
    if ass_path and Path(ass_path).exists():
        if re.search(r'[;,\[\]@]', str(ass_path)):
            raise ValueError(f"ASS subtitle path contains unsafe characters: {ass_path}")
        safe_ass = _ass_no_spaces(Path(ass_path), job_id)
        vf_parts.append(f"ass={safe_ass.name}")  # bare filename only
        ffmpeg_cwd = str(safe_ass.parent)          # run ffmpeg from that dir
    vf = ",".join(vf_parts) if vf_parts else None

    if music_path and Path(music_path).exists():
        # Three inputs: video, voiceover, music
        cmd = ["ffmpeg", "-i", str(merged_video), "-i", str(voiceover)]

        # Loop music to match video duration, apply ducking
        music_filter = f"[2:a]aloop=loop=-1:size=2e+09,atrim=0:{duration}"
        if duck_filter:
            music_filter += f",{duck_filter}"
        music_filter += "[music]"

        # Mix voiceover + ducked music
        audio_filter = f"{music_filter};[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"

        cmd += [
            "-stream_loop", "-1", "-i", str(music_path),
            "-filter_complex", audio_filter,
        ]

        if vf:
            cmd += ["-vf", vf]

        cmd += [
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(out_path), "-y", "-loglevel", "quiet",
        ]
    else:
        # Two inputs: video + voiceover (no music)
        cmd = ["ffmpeg", "-i", str(merged_video), "-i", str(voiceover)]

        if vf:
            cmd += ["-vf", vf]

        cmd += [
            "-c:v", "libx264" if vf else "copy",
            "-c:a", "aac", "-shortest",
            str(out_path), "-y", "-loglevel", "quiet",
        ]

    run_cmd(cmd, cwd=ffmpeg_cwd)
    log(f"Video assembled: {out_path}")
    return out_path
