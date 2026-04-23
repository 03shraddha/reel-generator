"""Exa web search topic source — requires EXA_API_KEY env var or config.json.

Searches the live web for recent STEM/tech/science news and returns the most
relevant results as TopicCandidates. Gracefully skipped if key is absent.
Sign up at https://exa.ai to get an API key.
"""

from datetime import datetime, timedelta, timezone

import requests

from ..config import get_exa_key
from ..log import log
from .base import TopicCandidate, TopicSource

# Niche → Exa search query mapping
_NICHE_QUERIES: dict[str, str] = {
    "tech":    "latest AI machine learning technology startup breakthrough news",
    "science": "new scientific discovery physics biology chemistry space research",
    "gaming":  "new video game release announcement gaming news",
    "finance": "stock market economy finance news analysis",
    "fitness": "fitness health nutrition science research news",
    "beauty":  "beauty skincare health science news",
    "travel":  "travel destination discovery news",
    "general": "trending science technology STEM news today",
}

_EXA_SEARCH_URL = "https://api.exa.ai/search"


class ExaSource(TopicSource):
    """Search the live web via Exa's neural search API for recent news."""

    name = "exa"

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._api_key = get_exa_key()
        # Allow niche YAML or engine config to override the query
        self._query = config.get("query", "")
        self._niche = config.get("niche", "general")
        # How many days back to search (default: last 7 days for freshness)
        self._days_back = int(config.get("days_back", 7))

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def fetch_topics(self, limit: int = 10) -> list[TopicCandidate]:
        if not self._api_key:
            return []

        query = self._query or _NICHE_QUERIES.get(self._niche, _NICHE_QUERIES["general"])
        start_date = (
            datetime.now(timezone.utc) - timedelta(days=self._days_back)
        ).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        payload = {
            "query": query,
            "category": "news",
            "numResults": min(limit, 25),
            "startPublishedDate": start_date,
            "contents": {
                "text": {"maxCharacters": 300},
            },
        }

        try:
            resp = requests.post(
                _EXA_SEARCH_URL,
                json=payload,
                headers={
                    "x-api-key": self._api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "verticals/3.0",
                },
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as e:
            log(f"Exa fetch failed: {e}")
            return []

        candidates = []
        for i, item in enumerate(results[:limit]):
            title = (item.get("title") or "").strip()
            if not title:
                continue

            # Exa returns a relevance score (higher = more relevant)
            # Combine with rank decay for final trending_score
            exa_score = float(item.get("score") or 0.5)
            rank_decay = max(0.0, 1.0 - i * 0.04)
            trending_score = round(min(1.0, exa_score * rank_decay), 3)

            summary = (item.get("text") or "").strip()[:300]

            candidates.append(TopicCandidate(
                title=title,
                source="exa",
                trending_score=trending_score,
                summary=summary,
                url=item.get("url") or "",
                metadata={
                    "published_date": item.get("publishedDate", ""),
                    "exa_score": exa_score,
                },
            ))

        return candidates
