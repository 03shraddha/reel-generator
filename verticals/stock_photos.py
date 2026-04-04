"""Real-photo source via Wikimedia Commons — no API key required.

Fetches freely licensed photographs matching a keyword query.
Used as the preferred source before AI image generation.
"""

import requests
from pathlib import Path

from .log import log


def _search_wikimedia(query: str, limit: int = 5) -> list[str]:
    """Search Wikimedia Commons for real photos matching query. Returns list of image URLs."""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6,  # File namespace
        "gsrlimit": limit * 3,  # fetch extra to filter
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "iiurlwidth": 1080,
        "format": "json",
    }
    try:
        r = requests.get(url, params=params, timeout=15, headers={"User-Agent": "verticals/3.0"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log(f"Wikimedia search failed for '{query}': {e}")
        return []

    urls = []
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        info = page.get("imageinfo", [{}])[0]
        mime = info.get("mime", "")
        if mime not in ("image/jpeg", "image/png"):
            continue
        # Prefer the scaled thumbnail URL (iiurlwidth applied)
        img_url = info.get("thumburl") or info.get("url", "")
        if img_url:
            urls.append(img_url)
        if len(urls) >= limit:
            break

    return urls


def fetch_real_photo(query: str, output_path: Path, used_urls: set | None = None) -> bool:
    """Fetch one real photo from Wikimedia Commons for the given query keyword.

    Args:
        query: Search keyword for Wikimedia Commons.
        output_path: Where to save the downloaded image.
        used_urls: Set of already-used image URLs. Matching URLs are skipped
                   and the chosen URL is added to the set to prevent reuse.

    Returns True if successful, False if no photo found.
    """
    if used_urls is None:
        used_urls = set()
    urls = _search_wikimedia(query, limit=5)
    for img_url in urls:
        if img_url in used_urls:
            continue  # skip already-used photo
        try:
            r = requests.get(img_url, timeout=30, headers={"User-Agent": "verticals/3.0"})
            r.raise_for_status()
            if len(r.content) < 5000:  # skip tiny/broken images
                continue
            output_path.write_bytes(r.content)
            used_urls.add(img_url)  # mark as used so later frames skip it
            log(f"Real photo fetched from Wikimedia: {output_path.name}")
            return True
        except Exception as e:
            log(f"Failed to download {img_url}: {e}")
            continue
    return False


def extract_keyword(prompt: str) -> str:
    """Extract a short search keyword from a b-roll prompt."""
    # Take first 5 words, strip common cinematic terms
    skip = {"cinematic", "photorealistic", "high", "quality", "lighting", "dramatic",
            "professional", "portrait", "camera", "shot", "close-up", "wide", "aerial"}
    words = prompt.lower().split()
    keywords = [w.strip(".,;:") for w in words if w.strip(".,;:") not in skip]
    return " ".join(keywords[:4])
