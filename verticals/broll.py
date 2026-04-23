"""B-roll generation: fal.ai Kling video (primary) or GPT image + Ken Burns (fallback)."""

import base64
import os
from pathlib import Path

import requests
from PIL import Image

from .config import VIDEO_WIDTH, VIDEO_HEIGHT, run_cmd, get_fal_key
from .log import log
from .retry import with_retry

# Prepended to every b-roll prompt so the model produces real-looking photography
_HYPERREALISTIC_PREFIX = (
    "Ultra-hyperrealistic professional photograph. "
    "Shot on a Sony A7R V with an 85mm f/1.8 prime lens, ISO 400, natural ambient lighting. "
    "Must be completely indistinguishable from a real photograph — "
    "not AI-generated, not illustrated, not CGI, not digitally rendered. "
    "Photojournalistic quality: authentic textures, genuine depth of field, "
    "real-world lighting conditions, natural imperfections. Subject: "
)

# Model cascade: gpt-image-2 first (best quality), fall back to gpt-image-1
# size is the portrait dimension string for each model
_MODEL_CASCADE = [
    ("gpt-image-2", "1024x1792"),  # native 9:16 for gpt-image-2
    ("gpt-image-1", "1024x1536"),  # approximate 9:16 for gpt-image-1
]

# HTTP status codes that mean the model isn't accessible yet — triggers fallback
_FALLBACK_STATUSES = {403, 404, 429}


@with_retry(max_retries=2, base_delay=2.0)
def _call_images_api(prompt: str, output_path: Path, api_key: str, model: str, size: str):
    """Single attempt to generate an image with a specific model/size."""
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "prompt": prompt, "size": size, "n": 1, "quality": "high"},
        timeout=120,
        verify=True,
    )
    if r.status_code != 200:
        try:
            detail = r.json().get("error", {}).get("message", r.text[:300])
        except Exception:
            detail = r.text[:300]
        raise RuntimeError(f"[{r.status_code}] {detail}")

    data = r.json()
    img_b64 = data["data"][0].get("b64_json") or data["data"][0].get("url")
    if not img_b64:
        raise RuntimeError("No image data in response")

    if data["data"][0].get("b64_json"):
        output_path.write_bytes(base64.b64decode(img_b64))
    else:
        img_r = requests.get(img_b64, timeout=60, verify=True)
        img_r.raise_for_status()
        output_path.write_bytes(img_r.content)


def _generate_image_openai(prompt: str, output_path: Path, api_key: str):
    """Try gpt-image-2, fall back to gpt-image-1 if model isn't accessible yet."""
    full_prompt = _HYPERREALISTIC_PREFIX + prompt
    last_error = None

    for model, size in _MODEL_CASCADE:
        try:
            _call_images_api(full_prompt, output_path, api_key, model, size)
            if model != _MODEL_CASCADE[0][0]:
                log(f"Used fallback model {model}")
            return
        except RuntimeError as e:
            err = str(e)
            # Only fall through to next model on access/availability errors
            status_code = int(err[1:4]) if err.startswith("[") and err[4] == "]" else 0
            if status_code in _FALLBACK_STATUSES or any(
                kw in err.lower() for kw in ("not found", "does not exist", "no access", "permission")
            ):
                log(f"{model} not accessible yet ({err[:80]}) — trying fallback")
                last_error = e
                continue
            raise  # real error (bad prompt, auth failure, etc.) — don't mask it

    raise RuntimeError(f"All image models failed. Last error: {last_error}")


def _get_openai_key() -> str:
    """Read OpenAI key from env or config.json."""
    from .config import load_config
    return os.environ.get("OPENAI_API_KEY") or load_config().get("OPENAI_API_KEY", "")


def _fallback_frame(i: int, out_dir: Path) -> Path:
    """Solid colour fallback frame if Gemini fails."""
    colors = [(20, 20, 60), (40, 10, 40), (10, 30, 50)]
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), colors[i % len(colors)])
    path = out_dir / f"broll_{i}.png"
    img.save(path)
    return path


def _resize_to_portrait(img_path: Path):
    """Resize/crop an image to 9:16 portrait (VIDEO_WIDTH x VIDEO_HEIGHT) in place."""
    img = Image.open(img_path).convert("RGB")
    target_w, target_h = VIDEO_WIDTH, VIDEO_HEIGHT
    orig_w, orig_h = img.size
    scale = max(target_w / orig_w, target_h / orig_h)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))
    img.save(img_path)


def _generate_broll_fal(prompt: str, out_path: Path):
    """Generate a 5-second video clip via fal.ai Kling 1.6 (text-to-video, 9:16).

    Downloads the resulting MP4 to out_path.
    """
    import fal_client  # pip install fal-client

    # fal_client reads FAL_KEY from env; set it explicitly to use our config chain
    os.environ.setdefault("FAL_KEY", get_fal_key())

    log(f"Generating b-roll clip via fal.ai Kling 1.6: {prompt[:60]}...")
    result = fal_client.subscribe(
        "fal-ai/kling-video/v1.6/standard/text-to-video",
        arguments={
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "duration": "5",
        },
    )
    video_url = result["video"]["url"]
    resp = requests.get(video_url, timeout=120, verify=True)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)
    log(f"fal.ai clip saved: {out_path.name}")


def generate_broll(prompts: list, out_dir: Path) -> list[Path]:
    """Generate up to 10 b-roll frames/clips.

    Uses fal.ai Kling 1.6 (real video) when FAL_KEY is set; falls back to
    GPT-image-2 static images + Ken Burns if fal.ai is unavailable or fails.
    """
    fal_key = get_fal_key()
    openai_key = _get_openai_key()
    if not fal_key and not openai_key:
        raise RuntimeError("Either FAL_KEY or OPENAI_API_KEY is required for b-roll generation. Add one to .env")

    frames = []

    for i, prompt in enumerate(prompts[:10]):
        # Try fal.ai first (real video clip)
        if fal_key:
            clip_path = out_dir / f"broll_{i}.mp4"
            try:
                _generate_broll_fal(prompt, clip_path)
                frames.append(clip_path)
                continue
            except Exception as e:
                log(f"fal.ai clip {i+1} failed: {e} — falling back to OpenAI image")

        # Fall back to OpenAI static image
        out_path = out_dir / f"broll_{i}.png"
        log(f"Generating b-roll frame {i+1}/{len(prompts[:10])} via gpt-image-2...")
        try:
            _generate_image_openai(prompt, out_path, openai_key)
            _resize_to_portrait(out_path)
            frames.append(out_path)
        except Exception as e:
            log(f"gpt-image-2 frame {i+1} failed: {e} — using solid-colour fallback")
            frames.append(_fallback_frame(i, out_dir))

    # Pad to minimum 10 entries (solid-colour fallback images)
    while len(frames) < 10:
        idx = len(frames)
        log(f"Padding to meet 10-image minimum: adding fallback frame {idx+1}")
        frames.append(_fallback_frame(idx, out_dir))

    return frames


def animate_frame(img_path: Path, out_path: Path, duration: float, effect: str = "zoom_in"):
    """Ken Burns animation on a single frame."""
    fps = 30
    frames = int(duration * fps)
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT

    if effect == "zoom_in":
        vf = (
            f"scale={int(w * 1.12)}:{int(h * 1.12)},"
            f"zoompan=z='1.12-0.12*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={w}x{h}:fps={fps}"
        )
    elif effect == "pan_right":
        vf = (
            f"scale={int(w * 1.15)}:{int(h * 1.15)},"
            f"zoompan=z=1.15:x='0.15*iw*on/{frames}':y='ih*0.075'"
            f":d={frames}:s={w}x{h}:fps={fps}"
        )
    else:  # zoom_out
        vf = (
            f"scale={int(w * 1.12)}:{int(h * 1.12)},"
            f"zoompan=z='1.0+0.12*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={w}x{h}:fps={fps}"
        )

    run_cmd([
        "ffmpeg", "-loop", "1", "-i", str(img_path),
        "-vf", vf, "-t", str(duration), "-r", str(fps),
        "-pix_fmt", "yuv420p", str(out_path), "-y", "-loglevel", "quiet",
    ])
