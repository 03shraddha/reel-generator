"""B-roll image generation (gpt-image-1 primary, Gemini fallback) + Ken Burns animation."""

import base64
import os
from pathlib import Path

import requests
from PIL import Image

from .config import VIDEO_WIDTH, VIDEO_HEIGHT, get_gemini_key, run_cmd
from .log import log
from .retry import with_retry


# ─────────────────────────────────────────────────────
# OpenAI gpt-image-1 — primary provider when key available
# ─────────────────────────────────────────────────────

@with_retry(max_retries=3, base_delay=2.0)
def _generate_image_openai(prompt: str, output_path: Path, api_key: str):
    """Generate image via OpenAI gpt-image-1 (portrait 1024x1536)."""
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-image-1",
            "prompt": prompt,
            "size": "1024x1536",   # portrait — closest to 9:16
            "n": 1,
            "quality": "medium",   # balance cost vs quality
        },
        timeout=120,
        verify=True,
    )
    if r.status_code != 200:
        try:
            detail = r.json().get("error", {}).get("message", r.text[:300])
        except Exception:
            detail = r.text[:300]
        raise RuntimeError(f"OpenAI Images API {r.status_code}: {detail}")

    data = r.json()
    # gpt-image-1 returns base64 by default (no response_format needed)
    img_b64 = data["data"][0].get("b64_json") or data["data"][0].get("url")
    if not img_b64:
        raise RuntimeError("No image data in OpenAI response")

    if data["data"][0].get("b64_json"):
        output_path.write_bytes(base64.b64decode(img_b64))
    else:
        # URL fallback — download it
        img_r = requests.get(img_b64, timeout=60, verify=True)
        img_r.raise_for_status()
        output_path.write_bytes(img_r.content)


def _get_openai_key() -> str:
    """Read OpenAI key from env or config.json."""
    from .config import load_config
    return os.environ.get("OPENAI_API_KEY") or load_config().get("OPENAI_API_KEY", "")


# ─────────────────────────────────────────────────────
# Gemini Imagen — fallback provider
# ─────────────────────────────────────────────────────

@with_retry(max_retries=3, base_delay=2.0)
def _generate_image_gemini(prompt: str, output_path: Path, api_key: str):
    """Generate image via Gemini native image generation (free tier compatible)."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta"
        "/models/gemini-2.0-flash-preview-image-generation:generateContent"
    )
    body = {
        "contents": [{"parts": [{"text": f"Generate an image: {prompt}"}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    r = requests.post(
        url, json=body, timeout=90,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        verify=True,
    )
    if r.status_code != 200:
        try:
            detail = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            detail = r.text[:200]
        raise RuntimeError(f"Gemini API {r.status_code}: {detail}")
    data = r.json()
    # Extract image from response parts
    for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            img_b64 = part["inlineData"]["data"]
            output_path.write_bytes(base64.b64decode(img_b64))
            return
    raise RuntimeError("No image in Gemini response")


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


def generate_broll(prompts: list, out_dir: Path) -> list[Path]:
    """Generate up to 10 b-roll frames — gpt-image-1 primary, Gemini fallback, solid-colour last resort."""
    openai_key = _get_openai_key()
    frames = []

    for i, prompt in enumerate(prompts[:10]):
        out_path = out_dir / f"broll_{i}.png"
        generated = False

        # 1. Try OpenAI gpt-image-1
        if openai_key:
            log(f"Generating b-roll frame {i+1}/{len(prompts[:10])} via gpt-image-1...")
            try:
                _generate_image_openai(prompt, out_path, openai_key)
                _resize_to_portrait(out_path)
                frames.append(out_path)
                generated = True
            except Exception as e:
                log(f"gpt-image-1 frame {i+1} failed: {e} — trying Gemini")

        # 2. Try Gemini Imagen
        if not generated:
            gemini_key = get_gemini_key()
            if gemini_key:
                log(f"Generating b-roll frame {i+1}/{len(prompts[:10])} via Gemini Imagen...")
                try:
                    _generate_image_gemini(prompt, out_path, gemini_key)
                    _resize_to_portrait(out_path)
                    frames.append(out_path)
                    generated = True
                except Exception as e:
                    log(f"Gemini frame {i+1} failed: {e} — using fallback")

        if not generated:
            log(f"Frame {i+1}: using solid-colour fallback")
            frames.append(_fallback_frame(i, out_dir))

    # Validation: enforce minimum 10 frames (pad with fallback if needed)
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
