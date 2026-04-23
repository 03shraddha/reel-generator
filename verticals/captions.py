"""Whisper word-level timestamps + ASS subtitle generation + Pillow fallback."""

from pathlib import Path

from .log import log


def _deepgram_word_timestamps(audio_path: Path, lang: str = "en") -> list[dict]:
    """Get word-level timestamps from Deepgram Nova-3 (cloud, ~1-3s vs Whisper's 10-60s)."""
    from .config import get_deepgram_key
    api_key = get_deepgram_key()

    import requests

    log("Running Deepgram Nova-3 for word-level timestamps...")
    audio_bytes = audio_path.read_bytes()

    # Detect MIME type from extension
    ext = audio_path.suffix.lower()
    mime = {"mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4"}.get(ext.lstrip("."), "audio/mpeg")

    lang_code = lang[:2]
    r = requests.post(
        f"https://api.deepgram.com/v1/listen?model=nova-3&language={lang_code}&words=true&punctuate=true",
        headers={"Authorization": f"Token {api_key}", "Content-Type": mime},
        data=audio_bytes,
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Deepgram {r.status_code}: {r.text[:200]}")

    words_raw = (
        r.json()
        .get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
        .get("words", [])
    )
    words = [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in words_raw]
    log(f"Deepgram returned {len(words)} word timestamps.")
    return words


def _has_ass_filter() -> bool:
    """Check if ffmpeg has libass (for ASS subtitle burn-in)."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffmpeg", "-filters"],
            capture_output=True, text=True, timeout=5,
        )
        return "ass" in r.stdout
    except Exception:
        return False


def _whisper_word_timestamps(audio_path: Path, lang: str = "en", script: str = "") -> list[dict]:
    """Get word-level timestamps from Deepgram (if key set) or local Whisper.

    Args:
        audio_path: Path to audio file.
        lang: Language code.
        script: Original script text. Passed to Whisper as initial_prompt to
                improve transcription accuracy on synthesized speech.
                Not needed for Deepgram (it handles TTS audio well natively).

    Returns list of {"word": str, "start": float, "end": float}.
    """
    from .config import get_deepgram_key
    if get_deepgram_key():
        try:
            words = _deepgram_word_timestamps(audio_path, lang)
            if words and script:
                words = _align_script_words(script.split(), words)
            return words
        except Exception as e:
            log(f"Deepgram failed: {e} — falling back to Whisper")

    try:
        import whisper
    except ImportError:
        log("Whisper not installed — skipping word timestamps")
        return []

    log("Running Whisper for word-level timestamps...")
    model = whisper.load_model("small")
    transcribe_kwargs = {
        "language": lang[:2],
        "word_timestamps": True,
    }
    # Providing the script as initial_prompt significantly reduces transcription
    # errors on synthesized (TTS) audio — Whisper stays anchored to the right words.
    if script:
        transcribe_kwargs["initial_prompt"] = script[:900]  # ~224 tokens ≈ 900 English chars
    result = model.transcribe(str(audio_path), **transcribe_kwargs)

    whisper_words = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            whisper_words.append({
                "word": w["word"].strip(),
                "start": w["start"],
                "end": w["end"],
            })

    log(f"Got {len(whisper_words)} word timestamps.")

    if script and whisper_words:
        whisper_words = _align_script_words(script.split(), whisper_words)

    return whisper_words


def _align_script_words(script_words: list[str], whisper_words: list[dict]) -> list[dict]:
    """Align script words to Whisper timestamps using sequence matching.

    Matches script words to Whisper words with difflib, then interpolates
    timestamps for words Whisper missed. Result uses script spelling (no
    typos) with Whisper timing (accurate sync).
    """
    from difflib import SequenceMatcher

    def _norm(w: str) -> str:
        return w.lower().strip(".,!?;:'\"()-")

    s_norm = [_norm(w) for w in script_words]
    w_norm = [_norm(w["word"]) for w in whisper_words]

    matcher = SequenceMatcher(None, s_norm, w_norm, autojunk=False)

    # Map: script_idx -> whisper timestamp
    script_to_ts: dict[int, dict] = {}
    for s_start, w_start, length in matcher.get_matching_blocks():
        for offset in range(length):
            script_to_ts[s_start + offset] = whisper_words[w_start + offset]

    # Build result with None placeholders for unmatched words
    result: list[dict] = []
    for i, word in enumerate(script_words):
        if i in script_to_ts:
            ts = script_to_ts[i]
            result.append({"word": word, "start": ts["start"], "end": ts["end"]})
        else:
            result.append({"word": word, "start": None, "end": None})

    # Interpolate timestamps for words Whisper missed
    total_duration = whisper_words[-1]["end"] if whisper_words else 0.0
    _interpolate_missing(result, total_duration)

    log(f"Aligned {len(script_words)} script words: {len(script_to_ts)} matched, "
        f"{len(script_words) - len(script_to_ts)} interpolated.")
    return result


def _interpolate_missing(words: list[dict], total_duration: float) -> None:
    """Fill None timestamps by linear interpolation between known anchors."""
    n = len(words)
    anchors = [(i, w["start"], w["end"]) for i, w in enumerate(words) if w["start"] is not None]

    if not anchors:
        per = total_duration / max(n, 1)
        for i, w in enumerate(words):
            w["start"] = i * per
            w["end"] = (i + 1) * per
        return

    i = 0
    while i < n:
        if words[i]["start"] is not None:
            i += 1
            continue

        # Find the gap extent
        gap_end = i
        while gap_end + 1 < n and words[gap_end + 1]["start"] is None:
            gap_end += 1

        prev = next((a for a in reversed(anchors) if a[0] < i), None)
        nxt = next((a for a in anchors if a[0] > gap_end), None)

        # Use surrounding words' full span (start→end) so missed words
        # always get non-zero duration even when adjacent whisper words abut.
        t_start = prev[1] if prev else 0.0   # start of prev matched word
        t_end = nxt[2] if nxt else total_duration  # end of next matched word
        count = gap_end - i + 1 + 2  # +2 accounts for the anchor words sharing the span
        t_start = prev[2] if prev else 0.0   # revert to end of prev (gives missed words their own slice after prev)
        t_end = nxt[1] if nxt else total_duration
        # If gap is zero-width, steal a small slice proportional to word count
        if t_end <= t_start:
            slice_width = 0.1 * (gap_end - i + 1)
            t_start = max(0.0, t_start - slice_width / 2)
            t_end = t_start + slice_width
        count = gap_end - i + 1
        per = (t_end - t_start) / max(count, 1)

        for j in range(i, gap_end + 1):
            offset = j - i
            words[j]["start"] = t_start + offset * per
            words[j]["end"] = t_start + (offset + 1) * per

        i = gap_end + 1


def _group_words(words: list[dict], group_size: int = 4) -> list[list[dict]]:
    groups = []
    for i in range(0, len(words), group_size):
        groups.append(words[i:i + group_size])
    return groups


def _format_ass_time(seconds: float) -> str:
    """Format seconds to ASS timestamp: H:MM:SS.cc (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _generate_ass(words: list[dict], output_path: Path, video_width: int = 1080, video_height: int = 1920, highlight_color: str = "#FFFF00", group_size: int = 4, font_family: str = "Special Elite"):
    """Generate ASS subtitle file with word-by-word color highlighting.

    White text for inactive words, yellow for current word.
    Semi-transparent background, positioned at lower third (~70% down).
    """
    # ASS header
    margin_v = int(video_height * 0.25)  # ~75% down from top = 25% from bottom
    header = f"""[Script Info]
Title: Pipeline Captions
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_family},72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,3,3,0,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Convert hex color to ASS BGR format (e.g. #00FF88 -> 88FF00)
    hc = highlight_color.lstrip("#")
    if len(hc) == 6:
        ass_highlight = f"&H00{hc[4:6]}{hc[2:4]}{hc[0:2]}&"
    else:
        ass_highlight = "&H0000FFFF&"  # fallback yellow

    groups = _group_words(words, group_size=group_size)
    events = []

    for group in groups:
        if not group:
            continue

        group_start = group[0]["start"]
        group_end = group[-1]["end"]

        # For each word in the group being active, emit one dialogue line
        for active_idx, active_word in enumerate(group):
            start = active_word["start"]
            end = active_word["end"]

            # Build text with override tags: highlight color for active, white for rest
            parts = []
            for j, w in enumerate(group):
                if j == active_idx:
                    parts.append(f"{{\\c{ass_highlight}\\b1\\fs80}}{w['word']}{{\\r}}")
                else:
                    parts.append(w["word"])

            text = " ".join(parts)
            events.append(
                f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,,0,0,0,,{text}"
            )

    output_path.write_text(header + "\n".join(events), encoding="utf-8")
    log(f"ASS captions saved: {output_path.name}")
    return output_path


def _generate_srt(words: list[dict], output_path: Path, group_size: int = 4) -> Path:
    """Generate standard SRT file from word timestamps."""
    groups = _group_words(words, group_size=group_size)
    lines = []

    for i, group in enumerate(groups, 1):
        if not group:
            continue
        start = group[0]["start"]
        end = group[-1]["end"]
        text = " ".join(w["word"] for w in group)

        start_ts = _srt_time(start)
        end_ts = _srt_time(end)
        lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    log(f"SRT captions saved: {output_path.name}")
    return output_path


def _srt_time(seconds: float) -> str:
    """Format seconds to SRT timestamp: HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_captions(
    audio_path: Path,
    work_dir: Path,
    lang: str = "en",
    highlight_color: str = "#FFFF00",
    words_per_group: int = 4,
    font_family: str = "Special Elite",
    script: str = "",
) -> dict:
    """Generate captions: ASS (for burn-in) + SRT (for YouTube upload).

    Args:
        audio_path: Path to voiceover audio.
        work_dir: Directory to write caption files.
        lang: Language code.
        highlight_color: Hex color for the active (highlighted) word.
        words_per_group: Words shown per subtitle line.
        font_family: Font for ASS burn-in captions.
        script: Original script text. Passed to Whisper as initial_prompt to
                improve transcription accuracy on synthesized speech.

    Returns dict with keys: srt_path, ass_path, words (for music ducking).
    """
    words = _whisper_word_timestamps(audio_path, lang, script=script)

    result = {"words": words}

    if not words:
        log("No word timestamps — skipping caption generation")
        # Fallback: run whisper CLI for SRT only
        try:
            from .config import run_cmd
            run_cmd([
                "whisper", str(audio_path),
                "--model", "base",
                "--language", lang[:2],
                "--output_format", "srt",
                "--output_dir", str(work_dir),
            ], capture=True)
            candidates = list(work_dir.glob("*.srt"))
            if candidates:
                srt = candidates[0]
                final = audio_path.with_suffix(".srt")
                srt.rename(final)
                result["srt_path"] = str(final)
        except Exception as e:
            log(f"Whisper CLI fallback failed: {e}")
        return result

    # Generate SRT
    srt_path = work_dir / f"captions_{lang}.srt"
    _generate_srt(words, srt_path, group_size=words_per_group)
    result["srt_path"] = str(srt_path)

    # Generate ASS for burn-in (niche-aware highlight color)
    ass_path = work_dir / f"captions_{lang}.ass"
    _generate_ass(words, ass_path, highlight_color=highlight_color, group_size=words_per_group, font_family=font_family)
    result["ass_path"] = str(ass_path)

    return result
