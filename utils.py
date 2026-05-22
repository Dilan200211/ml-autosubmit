"""
Utility helpers for the MonsterLab ClipIt Telegram auto-submit bot.

Provides URL validation/extraction, platform detection, text formatting,
and Telegram MarkdownV2 escaping.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

# ── Platform emoji mapping ─────────────────────────────────────────────────
PLATFORM_EMOJIS: dict[str, str] = {
    "tiktok": "🎵",
    "instagram": "📸",
    "youtube": "▶️",
    "twitter": "🐦",
    "facebook": "📘",
    "unknown": "🔗",
}

# Domain fragments → canonical platform name
_DOMAIN_MAP: list[tuple[str, str]] = [
    ("tiktok.com", "tiktok"),
    ("instagram.com", "instagram"),
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
    ("twitter.com", "twitter"),
    ("x.com", "twitter"),
    ("facebook.com", "facebook"),
    ("fb.watch", "facebook"),
]

# Regex for pulling URLs out of free-form text.  Intentionally broad so
# that shortened / tracking URLs are also captured.
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"'`,;)\]]+",
    re.IGNORECASE,
)

# Characters that need escaping in Telegram MarkdownV2
_MD_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!\\"


# ── Public helpers ─────────────────────────────────────────────────────────


def is_valid_url(url: str) -> bool:
    """Return ``True`` if *url* looks like a valid HTTP(S) URL.

    Performs a lightweight structural check (scheme + netloc); does **not**
    make any network requests.

    >>> is_valid_url("https://www.tiktok.com/@user/video/123")
    True
    >>> is_valid_url("not-a-url")
    False
    """
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:  # noqa: BLE001
        return False


def detect_platform(url: str) -> str | None:
    """Detect the social-media platform from a URL's domain.

    Returns one of ``"tiktok"``, ``"instagram"``, ``"youtube"``,
    ``"twitter"``, ``"facebook"``, or ``None`` if no known platform
    matches.

    >>> detect_platform("https://www.tiktok.com/@user/video/123")
    'tiktok'
    >>> detect_platform("https://x.com/user/status/456")
    'twitter'
    >>> detect_platform("https://example.com")
    """
    try:
        hostname = urlparse(url.strip()).hostname or ""
        hostname = hostname.lower()
    except Exception:  # noqa: BLE001
        return None

    for domain_fragment, platform in _DOMAIN_MAP:
        if hostname == domain_fragment or hostname.endswith(f".{domain_fragment}"):
            return platform

    return None


def extract_urls(text: str) -> list[str]:
    """Extract all HTTP/HTTPS URLs from a text message.

    >>> extract_urls("Check https://tiktok.com/v/1 and https://youtu.be/abc")
    ['https://tiktok.com/v/1', 'https://youtu.be/abc']
    """
    return _URL_PATTERN.findall(text)


def format_earnings(amount: float) -> str:
    """Format a monetary amount as ``$XX.XX``.

    >>> format_earnings(4.5)
    '$4.50'
    >>> format_earnings(123)
    '$123.00'
    """
    return f"${amount:,.2f}"


def format_time_ago(dt: datetime) -> str:
    """Return a human-readable relative time string.

    If *dt* is naive it is assumed to be UTC.

    >>> from datetime import timedelta
    >>> now = datetime.now(timezone.utc)
    >>> format_time_ago(now - timedelta(seconds=30))
    'just now'
    >>> format_time_ago(now - timedelta(minutes=2))
    '2 min ago'
    >>> format_time_ago(now - timedelta(hours=1))
    '1 hour ago'
    >>> format_time_ago(now - timedelta(days=3))
    '3 days ago'
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    delta = datetime.now(timezone.utc) - dt
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        return "just now"

    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"

    hours = minutes // 60
    if hours < 24:
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit} ago"

    days = hours // 24
    unit = "day" if days == 1 else "days"
    return f"{days} {unit} ago"


def truncate(text: str, max_len: int = 50) -> str:
    """Truncate *text* to *max_len* characters, appending ``…`` if trimmed.

    >>> truncate("Hello world", 5)
    'Hell…'
    >>> truncate("Hi", 5)
    'Hi'
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def escape_md(text: str) -> str:
    r"""Escape special characters for Telegram MarkdownV2.

    Every character in ``_*[]()~\`>#+-=|{}.!\\`` is prefixed with ``\``.

    >>> escape_md("Hello_World!")
    'Hello\\_World\\!'
    """
    result: list[str] = []
    for ch in text:
        if ch in _MD_ESCAPE_CHARS:
            result.append("\\")
        result.append(ch)
    return "".join(result)


def platform_emoji(platform: str | None) -> str:
    """Return the emoji for a platform name, falling back to 🔗.

    >>> platform_emoji("tiktok")
    '🎵'
    >>> platform_emoji(None)
    '🔗'
    """
    if platform is None:
        return PLATFORM_EMOJIS["unknown"]
    return PLATFORM_EMOJIS.get(platform.lower(), PLATFORM_EMOJIS["unknown"])
