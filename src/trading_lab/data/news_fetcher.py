"""Fetch recent news headlines and article bodies for an instrument via yfinance.

REQ-LLM-008: News ingestion for LLM context enrichment.

Returns a list of {title, source, timestamp, url, body} dicts compatible with
SignalContext.news_headlines. Silently returns [] on any failure so
news being unavailable never blocks signal generation.

Article bodies are fetched from the article URL using httpx + BeautifulSoup.
Paywalled or bot-blocked articles gracefully fall back to headline-only.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MAX_HEADLINES = 5
_MAX_BODY_CHARS = 800  # chars of article body to pass to the LLM
_FETCH_TIMEOUT = 6     # seconds per article request

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


def _fetch_article_body(url: str) -> str:
    """Fetch and extract readable text from an article URL.

    Returns up to _MAX_BODY_CHARS of article body text, or empty string
    if the fetch fails or the page is paywalled/empty.
    """
    if not url:
        return ""
    try:
        import httpx
        from bs4 import BeautifulSoup

        resp = httpx.get(url, headers=_HEADERS, timeout=_FETCH_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise elements
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "figure", "noscript", "iframe"]):
            tag.decompose()

        # Extract paragraph text
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(" ", strip=True) for p in paragraphs)

        # Collapse whitespace and truncate
        text = " ".join(text.split())
        return text[:_MAX_BODY_CHARS].rsplit(" ", 1)[0] if len(text) > _MAX_BODY_CHARS else text

    except Exception as exc:
        logger.debug("Article body fetch failed for %s: %s", url, exc)
        return ""


def fetch_news(symbol: str) -> list[dict]:
    """Return up to 5 recent news items (headline + article body) for the given yfinance symbol.

    Args:
        symbol: yfinance symbol, e.g. "GC=F".

    Returns:
        List of dicts with keys: title, source, timestamp, url, body.
        Empty list if yfinance returns nothing or raises.
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        raw = ticker.news or []
    except Exception as exc:
        logger.debug("News fetch failed for %s: %s", symbol, exc)
        return []

    headlines = []
    for item in raw[:_MAX_HEADLINES]:
        try:
            # yfinance >= 0.2.38 nests data under a 'content' key
            content = item.get("content") or item
            title = content.get("title", "")
            source = (content.get("provider") or {}).get("displayName", "") or content.get("publisher", "")
            pub_date = content.get("pubDate") or ""
            ts_str = pub_date[:10] if pub_date else ""  # "YYYY-MM-DD" from ISO string
            url = (content.get("canonicalUrl") or content.get("clickThroughUrl") or {}).get("url", "")
            if title:
                body = _fetch_article_body(url)
                headlines.append({
                    "title": title,
                    "source": source,
                    "timestamp": ts_str,
                    "url": url,
                    "body": body,
                })
        except Exception:
            continue

    logger.debug("Fetched %d article(s) for %s", len(headlines), symbol)
    return headlines
