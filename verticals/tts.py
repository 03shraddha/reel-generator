"""Multi-provider TTS — Edge TTS (free default), ElevenLabs (premium), macOS say (fallback).

Edge TTS is the recommended default: free, cross-platform, 300+ voices, no API key.
ElevenLabs is premium: most natural, requires API key.
macOS say is the last-resort fallback.
"""

import os
import sys
from pathlib import Path

import requests

from .config import VOICE_ID_EN, VOICE_ID_HI, get_elevenlabs_key, get_sarvam_key, run_cmd
from .log import log
from .retry import with_retry


# ─────────────────────────────────────────────────────
# Edge TTS — free, cross-platform, 300+ voices
# ─────────────────────────────────────────────────────

# Default Edge TTS voices per language
EDGE_VOICES = {
    "en": "en-US-GuyNeural",
    "hi": "hi-IN-MadhurNeural",
    "es": "es-MX-JorgeNeural",
    "pt": "pt-BR-AntonioNeural",
    "de": "de-DE-ConradNeural",
    "fr": "fr-FR-HenriNeural",
    "ja": "ja-JP-KeitaNeural",
    "ko": "ko-KR-InJoonNeural",
}

# Default speech rate — slightly accelerated for Shorts (fits more content, still clear)
DEFAULT_EDGE_RATE = "+15%"


async def _edge_tts_generate(text: str, voice: str, output_path: Path, rate: str = ""):
    """Generate audio via edge-tts (async)."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate or DEFAULT_EDGE_RATE)
    await communicate.save(str(output_path))


def _generate_edge_tts(script: str, out_dir: Path, lang: str, voice_override: str = "", rate: str = "") -> Path:
    """Generate voiceover via Edge TTS (free Microsoft voices)."""
    import asyncio

    voice = voice_override or EDGE_VOICES.get(lang[:2], EDGE_VOICES["en"])
    out_path = out_dir / f"voiceover_{lang}.mp3"

    log(f"Generating {lang} voiceover via Edge TTS (voice: {voice}, rate: {rate or DEFAULT_EDGE_RATE})...")

    try:
        # Handle event loop — works whether called from sync or async context
        try:
            loop = asyncio.get_running_loop()
            # Already in an async context, create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    _edge_tts_generate(script, voice, out_path, rate)
                )
                future.result(timeout=60)
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            asyncio.run(_edge_tts_generate(script, voice, out_path, rate))

        log(f"Edge TTS voiceover saved: {out_path.name}")
        return out_path
    except Exception as e:
        raise RuntimeError(f"Edge TTS failed: {e}")


# ─────────────────────────────────────────────────────
# ElevenLabs — premium, most natural
# ─────────────────────────────────────────────────────

@with_retry(max_retries=3, base_delay=2.0)
def _call_elevenlabs(script: str, voice_id: str, api_key: str, settings: dict | None = None) -> bytes:
    """Call ElevenLabs TTS API and return audio bytes."""
    voice_settings = settings or {
        "stability": 0.4,
        "similarity_boost": 0.85,
        "style": 0.3,
        "use_speaker_boost": True,
    }
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={
            "text": script,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": voice_settings,
        },
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    return r.content


def _generate_elevenlabs(
    script: str, out_dir: Path, lang: str,
    voice_id: str = "", settings: dict | None = None
) -> Path:
    """Generate voiceover via ElevenLabs."""
    api_key = get_elevenlabs_key()
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    vid = voice_id or (VOICE_ID_HI if lang == "hi" else VOICE_ID_EN)
    out_path = out_dir / f"voiceover_{lang}.mp3"

    log(f"Generating {lang} voiceover via ElevenLabs (voice: {vid})...")
    audio_bytes = _call_elevenlabs(script, vid, api_key, settings)
    out_path.write_bytes(audio_bytes)
    log(f"ElevenLabs voiceover saved: {out_path.name}")
    return out_path


# ─────────────────────────────────────────────────────
# Sarvam AI — bulbul:v3, 45 Indian-language voices
# ─────────────────────────────────────────────────────

# Default Sarvam voice per language
SARVAM_VOICES = {
    "en": "ishita",   # young female, energetic
    "hi": "ishita",
    "bn": "ishita",
    "gu": "ishita",
    "kn": "ishita",
    "ml": "ishita",
    "mr": "ishita",
    "od": "ishita",
    "pa": "ishita",
    "ta": "ishita",
    "te": "ishita",
}

# Sarvam language code mapping (ISO 639-1 → BCP-47)
SARVAM_LANG_CODES = {
    "en": "en-IN", "hi": "hi-IN", "bn": "bn-IN",
    "gu": "gu-IN", "kn": "kn-IN", "ml": "ml-IN",
    "mr": "mr-IN", "od": "od-IN", "pa": "pa-IN",
    "ta": "ta-IN", "te": "te-IN",
}

_SARVAM_MAX_CHARS = 2500


def _chunk_text(text: str, max_chars: int = _SARVAM_MAX_CHARS) -> list[str]:
    """Split text into chunks at sentence boundaries, staying under max_chars."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks, current = [], ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            # Single sentence longer than limit — hard split
            while len(sentence) > max_chars:
                chunks.append(sentence[:max_chars])
                sentence = sentence[max_chars:]
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def _parse_pace(val, default: float = 1.15) -> float:
    """Convert pace value to float — YAML niche profiles store it as a descriptive string."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


@with_retry(max_retries=3, base_delay=2.0)
def _call_sarvam(text: str, lang_code: str, speaker: str, api_key: str,
                 pace: float = 1.15, temperature: float = 0.7) -> bytes:
    """Call Sarvam AI TTS API and return raw WAV bytes."""
    import base64
    r = requests.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={
            "api-subscription-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "target_language_code": lang_code,
            "model": "bulbul:v3",
            "speaker": speaker,
            "pace": pace,
            "temperature": temperature,
            "speech_sample_rate": 24000,
        },
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Sarvam AI TTS {r.status_code}: {r.text[:200]}")
    audio_b64 = r.json()["audios"][0]
    return base64.b64decode(audio_b64)


def _generate_sarvam(
    script: str, out_dir: Path, lang: str,
    speaker: str = "", pace: float = 1.15, temperature: float = 0.7,
) -> Path:
    """Generate voiceover via Sarvam AI bulbul:v3 (young female voice by default)."""
    api_key = get_sarvam_key()
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY not set")

    lang2 = lang[:2].lower()
    lang_code = SARVAM_LANG_CODES.get(lang2, "en-IN")
    voice = speaker or SARVAM_VOICES.get(lang2, "ishita")

    log(f"Generating {lang} voiceover via Sarvam AI (speaker: {voice}, pace: {pace})...")

    chunks = _chunk_text(script)
    wav_paths: list[Path] = []

    for i, chunk in enumerate(chunks):
        wav_bytes = _call_sarvam(chunk, lang_code, voice, api_key, pace, temperature)
        chunk_path = out_dir / f"sarvam_chunk_{i}.wav"
        chunk_path.write_bytes(wav_bytes)
        wav_paths.append(chunk_path)

    out_path = out_dir / f"voiceover_{lang}.wav"

    if len(wav_paths) == 1:
        wav_paths[0].rename(out_path)
    else:
        # Concatenate WAV chunks with ffmpeg
        concat_list = out_dir / "sarvam_concat.txt"
        concat_list.write_text("\n".join(f"file '{p.name}'" for p in wav_paths))
        run_cmd([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c", "copy",
            str(out_path), "-y", "-loglevel", "quiet",
        ])
        for p in wav_paths:
            p.unlink(missing_ok=True)
        concat_list.unlink(missing_ok=True)

    log(f"Sarvam AI voiceover saved: {out_path.name}")
    return out_path


# ─────────────────────────────────────────────────────
# macOS say — last resort fallback
# ─────────────────────────────────────────────────────

def _generate_say(script: str, out_dir: Path) -> Path:
    """macOS 'say' fallback TTS."""
    if sys.platform != "darwin":
        raise RuntimeError(
            "No TTS provider available. Edge TTS failed and 'say' is macOS-only.\n"
            "Fix: pip install --upgrade edge-tts"
        )
    # Remove non-printable characters and cap length to prevent unexpected behaviour
    sanitized = "".join(c for c in script if c.isprintable())[:5000]
    out_path = out_dir / "voiceover_say.aiff"
    mp3_path = out_dir / "voiceover_say.mp3"
    run_cmd(["say", "-o", str(out_path), sanitized])
    run_cmd([
        "ffmpeg", "-i", str(out_path), "-acodec", "libmp3lame",
        str(mp3_path), "-y", "-loglevel", "quiet",
    ])
    return mp3_path


# ─────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────

def get_tts_provider(name: str | None = None) -> str:
    """Resolve which TTS provider to use.

    Priority: explicit name > TTS_PROVIDER env > auto-detect.
    Auto-detect tries: edge_tts > elevenlabs > say.
    """
    if name and name != "auto":
        return name.lower()

    from_env = os.environ.get("TTS_PROVIDER", "").lower()
    if from_env:
        return from_env

    from .config import load_config
    from_cfg = load_config().get("TTS_PROVIDER", "").lower()
    if from_cfg:
        return from_cfg

    # Auto-detect: paid API keys take priority over free defaults
    if get_sarvam_key():
        return "sarvam"

    if get_elevenlabs_key():
        return "elevenlabs"

    # Edge TTS free fallback (cross-platform)
    try:
        import edge_tts  # noqa: F401
        return "edge"
    except ImportError:
        pass

    # macOS say as last resort
    import shutil
    if shutil.which("say"):
        return "say"

    raise RuntimeError(
        "No TTS provider available. Install one:\n"
        "  pip install edge-tts  (free, recommended)\n"
        "  Set SARVAM_API_KEY (Indian-language voices)\n"
        "  Set ELEVENLABS_API_KEY (premium)\n"
        "  Or use macOS (has built-in 'say')"
    )


def generate_voiceover(
    script: str,
    out_dir: Path,
    lang: str = "en",
    provider: str | None = None,
    voice_config: dict | None = None,
) -> Path:
    """Generate voiceover via the configured TTS provider.

    Args:
        script: The voiceover text.
        out_dir: Directory to save the audio file.
        lang: Language code (en, hi, es, etc.).
        provider: TTS provider name (edge, elevenlabs, say).
        voice_config: Optional voice config from niche profile.

    Returns:
        Path to the generated audio file.
    """
    provider = get_tts_provider(provider)
    voice_config = voice_config or {}

    if provider == "edge":
        voice_override = voice_config.get("voice_id", "")
        rate = voice_config.get("rate", "")
        try:
            return _generate_edge_tts(script, out_dir, lang, voice_override, rate)
        except Exception as e:
            log(f"Edge TTS failed: {e}")
            # Fall through to next provider
            if get_elevenlabs_key():
                log("Falling back to ElevenLabs...")
                provider = "elevenlabs"
            else:
                log("Falling back to macOS say...")
                return _generate_say(script, out_dir)

    if provider == "sarvam":
        try:
            return _generate_sarvam(
                script, out_dir, lang,
                speaker=voice_config.get("voice_id", ""),
                pace=_parse_pace(voice_config.get("pace", 1.15)),
                temperature=voice_config.get("temperature", 0.7),
            )
        except Exception as e:
            log(f"Sarvam AI TTS failed: {e}")
            log("Falling back to Edge TTS...")
            return _generate_edge_tts(script, out_dir, lang)

    if provider == "elevenlabs":
        try:
            return _generate_elevenlabs(
                script, out_dir, lang,
                voice_id=voice_config.get("voice_id", ""),
                settings=voice_config.get("settings"),
            )
        except Exception as e:
            log(f"ElevenLabs failed: {e}")
            log("Falling back to macOS say...")
            return _generate_say(script, out_dir)

    if provider == "say":
        return _generate_say(script, out_dir)

    raise ValueError(f"Unknown TTS provider: {provider}")
