"""
modules/researcher.py — Trending Topic Finder
=============================================
Priority order:
  1. Tavily web search (when api_keys.tavily is configured)
  2. Google Trends via pytrends (real-time top queries)
  3. RSS feeds fallback (TechCrunch, The Verge, Ars Technica)

Returns a single string — the best trending AI/Tech topic to create a Short about.
"""

import os
import random
import time
import feedparser
import requests
from pytrends.request import TrendReq

from config import get_logger, DEFAULT_TOPICS
from core.config_manager import config

log = get_logger("researcher")

# ── RSS Feed URLs (AI/Tech) ────────────────────────────────────────────────────
RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://venturebeat.com/feed/",
    "https://www.wired.com/feed/rss",
]

# Keywords used to filter for AI/Tech relevance
AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "gpt", "llm", "robot", "automation", "neural", "tech", "openai",
    "google", "microsoft", "nvidia", "chip", "quantum", "model", "agent",
]


def _is_ai_tech(text: str) -> bool:
    """Return True if text contains at least one AI/tech keyword."""
    lower = text.lower()
    return any(kw in lower for kw in AI_KEYWORDS)


def get_tavily_api_key() -> str:
    """Resolve Tavily key from nested config, flat key, or env."""
    return (
        (config.get("api_keys.tavily", "") or "")
        or (config.get("tavily_api_key", "") or "")
        or os.environ.get("TAVILY_API_KEY", "")
    ).strip()


def _fetch_from_tavily(query: str = "latest trending AI technology news today") -> str | None:
    """Fetch a trending AI/Tech headline via Tavily web search."""
    tavily_key = get_tavily_api_key()
    if not tavily_key:
        log.debug("Tavily API key not configured — skipping web search")
        return None

    try:
        from tavily import TavilyClient

        log.info("Tavily search: %r …", query)
        client = TavilyClient(api_key=tavily_key)
        result = client.search(
            query=query,
            search_depth="basic",
            max_results=5,
            topic="news",
        )
        for hit in result.get("results", []):
            title = (hit.get("title") or "").strip()
            if title and _is_ai_tech(title):
                log.info("Tavily → chosen topic: %r", title)
                return title
        answer = (result.get("answer") or "").strip()
        if answer and _is_ai_tech(answer):
            headline = answer.split(".")[0].strip()[:160]
            if headline:
                log.info("Tavily answer → chosen topic: %r", headline)
                return headline
    except Exception as exc:
        log.warning("Tavily search failed: %s", exc)
    return None


def _fetch_from_pytrends() -> str | None:
    """Fetch the top trending AI/Tech search query from Google Trends."""
    try:
        log.debug("Querying Google Trends …")
        pytrends = TrendReq(hl="en-US", tz=330)

        # Get real-time trending searches (US)
        trending_df = pytrends.trending_searches(pn="united_states")
        candidates = trending_df[0].tolist()

        # Filter for AI/tech topics
        ai_topics = [t for t in candidates if _is_ai_tech(t)]
        if ai_topics:
            chosen = ai_topics[0]
            log.info(f"pytrends → chosen topic: {chosen!r}")
            return chosen

        # If nothing matched, try a keyword-based related query
        pytrends.build_payload(["artificial intelligence"], cat=0, timeframe="now 1-d")
        related = pytrends.related_queries()
        top_queries = related.get("artificial intelligence", {}).get("top")
        if top_queries is not None and not top_queries.empty:
            chosen = top_queries.iloc[0]["query"]
            log.info(f"pytrends related → chosen topic: {chosen!r}")
            return chosen

    except Exception as exc:
        log.debug(f"pytrends unavailable ({exc}) — falling back to RSS silently")
    return None


def _fetch_from_rss() -> str | None:
    """Scrape RSS feeds and return the most relevant AI/Tech headline."""
    log.debug("Fetching from RSS feeds …")
    headlines: list[str] = []

    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                if _is_ai_tech(title):
                    headlines.append(title)
        except Exception as exc:
            log.warning(f"RSS parse error ({url}): {exc}")

    if headlines:
        chosen = random.choice(headlines)
        log.info(f"RSS → chosen topic: {chosen!r}")
        return chosen

    return None


def find_trending_topic() -> str:
    """
    Public entry point — returns a trending AI/Tech topic string.
    Tries Tavily (if configured), then pytrends, RSS, then a safe default.
    """
    topic = _fetch_from_tavily()
    if not topic:
        topic = _fetch_from_pytrends()
    if not topic:
        topic = _fetch_from_rss()
    if not topic:
        topic = random.choice(DEFAULT_TOPICS)
        log.warning(f"All sources failed — using random default topic: {topic!r}")

    return topic


if __name__ == "__main__":
    # Quick smoke-test
    print(f"\n🔥 Trending topic: {find_trending_topic()}")
