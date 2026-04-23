"""Thumbnail generation — gpt-image-2, fallback to gpt-image-1 (16:9) + Pillow text overlay."""

import base64
import os
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from .config import load_config
from .log import log
from .retry import with_retry

_HYPERREALISTIC_PREFIX = (
    "Ultra-hyperrealistic professional photograph, 16:9 landscape YouTube thumbnail. "
    "Shot on a Sony A7R V, natural cinematic lighting. "
    "Must look like a real photograph — not AI-generated, not illustrated, not CGI. "
    "Photojournalistic quality with authentic textures and genuine depth of field. Subject: "
)

# Model cascade: gpt-image-2 first, fall back to gpt-image-1
_MODEL_CASCADE = [
    ("gpt-image-2", "1792x1024"),  # native 16:9 for gpt-image-2
    ("gpt-image-1", "1536x1024"),  # approximate 16:9 for gpt-image-1
]

_FALLBACK_STATUSES = {403, 404, 429}


def _get_openai_key() -> str:
    return os.environ.get("OPENAI_API_KEY") or load_config().get("OPENAI_API_KEY", "")

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720


@with_retry(max_retries=2, base_delay=2.0)
def _call_thumb_api(prompt: str, output_path: Path, api_key: str, model: str, size: str):
    """Single attempt to generate a thumbnail with a specific model/size."""
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "prompt": prompt, "n": 1, "size": size, "quality": "high"},
        timeout=120,
    )
    if r.status_code != 200:
        try:
            detail = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            detail = r.text[:200]
        raise RuntimeError(f"[{r.status_code}] {detail}")

    data = r.json()
    img_b64 = (data.get("data") or [{}])[0].get("b64_json")
    if not img_b64:
        raise RuntimeError("No image data in response")
    output_path.write_bytes(base64.b64decode(img_b64))


def _generate_thumb_image_openai(prompt: str, output_path: Path, api_key: str):
    """Try gpt-image-2, fall back to gpt-image-1 if model isn't accessible yet."""
    full_prompt = _HYPERREALISTIC_PREFIX + prompt
    last_error = None

    for model, size in _MODEL_CASCADE:
        try:
            _call_thumb_api(full_prompt, output_path, api_key, model, size)
            if model != _MODEL_CASCADE[0][0]:
                log(f"Used fallback model {model}")
            return
        except RuntimeError as e:
            err = str(e)
            status_code = int(err[1:4]) if err.startswith("[") and err[4] == "]" else 0
            if status_code in _FALLBACK_STATUSES or any(
                kw in err.lower() for kw in ("not found", "does not exist", "no access", "permission")
            ):
                log(f"{model} not accessible yet ({err[:80]}) — trying fallback")
                last_error = e
                continue
            raise

    raise RuntimeError(f"All image models failed. Last error: {last_error}")


def _overlay_title(image_path: Path, title: str, output_path: Path):
    """Overlay bold title text with drop shadow on the thumbnail."""
    img = Image.open(image_path).convert("RGB")
    img = img.resize((THUMB_WIDTH, THUMB_HEIGHT), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    # Try to find a bold font, fall back to default
    font_size = 64
    font = None
    for font_name in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        try:
            font = ImageFont.truetype(font_name, font_size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()

    # Word wrap the title
    max_width = THUMB_WIDTH - 80  # 40px padding each side
    lines = _wrap_text(draw, title, font, max_width)
    text_block = "\n".join(lines)

    # Calculate position (center, lower third)
    bbox = draw.multiline_textbbox((0, 0), text_block, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (THUMB_WIDTH - text_w) // 2
    y = THUMB_HEIGHT - text_h - 60  # 60px from bottom

    # Drop shadow
    shadow_offset = 3
    draw.multiline_text(
        (x + shadow_offset, y + shadow_offset),
        text_block, fill=(0, 0, 0), font=font, align="center",
    )

    # Main text
    draw.multiline_text(
        (x, y), text_block, fill=(255, 255, 255), font=font, align="center",
    )

    img.save(output_path)


def _wrap_text(draw: ImageDraw.Draw, text: str, font, max_width: int) -> list[str]:
    """Simple word-wrap for Pillow text rendering."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_thumbnail(draft: dict, out_dir: Path) -> Path:
    """Generate a YouTube thumbnail via gpt-image-1 + text overlay.

    Uses the thumbnail_prompt from the draft, overlays the video title.
    Returns path to the final thumbnail PNG.
    """
    openai_key = _get_openai_key()
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY is required for thumbnail generation. Add it to .env")

    prompt = draft.get("thumbnail_prompt", "Cinematic YouTube thumbnail")
    title = draft.get("youtube_title", draft.get("news", ""))
    job_id = draft.get("job_id", "unknown")

    raw_path = out_dir / f"thumb_raw_{job_id}.png"
    final_path = out_dir / f"thumb_{job_id}.png"

    log("Generating thumbnail via gpt-image-1...")
    _generate_thumb_image_openai(prompt, raw_path, openai_key)

    log("Adding title overlay...")
    _overlay_title(raw_path, title, final_path)

    log(f"Thumbnail saved: {final_path.name}")
    return final_path
