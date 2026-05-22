"""
MonsterLab ClipIt API Client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Async API client for the MonsterLab ClipIt platform using aiohttp.

Usage::

    async with MonsterLabAPI(api_key="ml_xxxx") as api:
        # Validate the API key (public endpoint, no auth needed)
        is_valid = await api.validate_key()

        # Fetch available campaigns
        campaigns = await api.get_campaigns()

        # Submit a clip
        result = await api.submit_clip(
            url="https://tiktok.com/@user/video/123",
            campaign_id="camp_123456",
        )
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class MonsterLabError(Exception):
    """Base exception for all MonsterLab API errors."""

    def __init__(self, message: str, status: int | None = None, response_body: Any = None) -> None:
        self.status = status
        self.response_body = response_body
        super().__init__(message)


class AuthError(MonsterLabError):
    """Raised on 401 / 403 – invalid or missing API key."""


class RateLimitError(MonsterLabError):
    """Raised on 429 – rate limit exceeded after all retries are exhausted."""

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
        **kwargs: Any,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


class SubmissionError(MonsterLabError):
    """Raised when a clip submission is explicitly rejected by the API."""


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateLimitInfo:
    """Parsed rate-limit headers from the most recent API response."""

    limit: int | None = None
    remaining: int | None = None
    reset: float | None = None  # Unix timestamp


@dataclass(frozen=True)
class ValidationResult:
    """Result of the ``/api/validate`` endpoint."""

    valid: bool


@dataclass(frozen=True)
class SubmissionResult:
    """Result of the ``/api/clips/submit`` endpoint."""

    submission_id: str
    status: str
    platform: str
    handle: str
    original_url: str


@dataclass(frozen=True)
class Campaign:
    """A single campaign returned by ``/api/clips/campaigns``."""

    campaign_id: str
    name: str
    type: str
    description: str
    payout_rates: Dict[str, float]
    platforms: List[str]


@dataclass
class AccountInfo:
    """Generic container for ``/api/account/*`` responses."""

    data: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL = "https://monsterlab.io"
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds
_BACKOFF_FACTOR = 2.0


class MonsterLabAPI:
    """Async client for the MonsterLab ClipIt API.

    Parameters
    ----------
    api_key:
        Your MonsterLab API key (``ml_xxxx``).
    base_url:
        Override the default API base URL.  Useful for testing against a
        local / staging server.
    """

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self._rate_limit_info: RateLimitInfo = RateLimitInfo()

    # -- Async context manager ------------------------------------------------

    async def __aenter__(self) -> "MonsterLabAPI":
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"ApiKey {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        logger.debug("MonsterLabAPI session opened.")
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("MonsterLabAPI session closed.")

    # -- Properties -----------------------------------------------------------

    @property
    def last_rate_limit_info(self) -> RateLimitInfo:
        """Return the rate-limit information parsed from the last API response."""
        return self._rate_limit_info

    # -- Internal helpers -----------------------------------------------------

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise MonsterLabError(
                "Session is not open. Use 'async with MonsterLabAPI(...) as api:' "
                "to manage the session lifecycle."
            )
        return self._session

    @staticmethod
    def _parse_rate_limit_headers(headers: aiohttp.typedefs.CIMultiDictProxy[str]) -> RateLimitInfo:
        """Extract ``X-RateLimit-*`` headers into a :class:`RateLimitInfo`."""

        def _safe_int(val: str | None) -> int | None:
            if val is None:
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                return None

        def _safe_float(val: str | None) -> float | None:
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        return RateLimitInfo(
            limit=_safe_int(headers.get("X-RateLimit-Limit")),
            remaining=_safe_int(headers.get("X-RateLimit-Remaining")),
            reset=_safe_float(headers.get("X-RateLimit-Reset")),
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Dict[str, Any]:
        """Send an HTTP request with automatic retry on 429 / 5xx.

        Parameters
        ----------
        method:
            HTTP method (``GET``, ``POST``, …).
        path:
            URL path appended to ``base_url`` (e.g. ``/api/clips/submit``).
        json_body:
            Optional JSON payload for POST requests.
        auth:
            Whether to include the ``Authorization`` header.  Set to
            ``False`` for public endpoints like ``/api/validate``.

        Returns
        -------
        dict
            Parsed JSON response body.
        """
        session = self._ensure_session()
        url = f"{self._base_url}{path}"

        headers: Dict[str, str] = {}
        if not auth:
            # For public endpoints, override the session-level auth header.
            headers["Authorization"] = ""

        last_exception: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            logger.debug(
                "Request %s %s (attempt %d/%d)",
                method,
                url,
                attempt,
                _MAX_RETRIES,
            )

            try:
                async with session.request(
                    method,
                    url,
                    json=json_body,
                    headers=headers if headers else None,
                ) as resp:
                    # Always update rate-limit info regardless of status.
                    self._rate_limit_info = self._parse_rate_limit_headers(resp.headers)

                    body: Dict[str, Any] = {}
                    try:
                        body = await resp.json(content_type=None)
                    except Exception:
                        body = {"_raw": await resp.text()}

                    logger.debug(
                        "Response %d | rate-limit remaining=%s",
                        resp.status,
                        self._rate_limit_info.remaining,
                    )

                    # --- Success ---
                    if resp.status < 400:
                        return body

                    # --- Auth errors (no retry) ---
                    if resp.status in (401, 403):
                        raise AuthError(
                            f"Authentication failed ({resp.status}): "
                            f"{body.get('message', body.get('error', resp.reason))}",
                            status=resp.status,
                            response_body=body,
                        )

                    # --- Rate limit ---
                    if resp.status == 429:
                        retry_after = _parse_retry_after(resp.headers, attempt)
                        logger.warning(
                            "Rate-limited (429). Retrying in %.1fs…",
                            retry_after,
                        )
                        last_exception = RateLimitError(
                            "Rate limit exceeded",
                            retry_after=retry_after,
                            status=429,
                            response_body=body,
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    # --- Server errors (5xx) ---
                    if resp.status >= 500:
                        wait = _BACKOFF_BASE * (_BACKOFF_FACTOR ** (attempt - 1))
                        logger.warning(
                            "Server error %d. Retrying in %.1fs…",
                            resp.status,
                            wait,
                        )
                        last_exception = MonsterLabError(
                            f"Server error ({resp.status})",
                            status=resp.status,
                            response_body=body,
                        )
                        await asyncio.sleep(wait)
                        continue

                    # --- Other client errors (no retry) ---
                    raise MonsterLabError(
                        f"API error ({resp.status}): "
                        f"{body.get('message', body.get('error', resp.reason))}",
                        status=resp.status,
                        response_body=body,
                    )

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                wait = _BACKOFF_BASE * (_BACKOFF_FACTOR ** (attempt - 1))
                logger.warning(
                    "Network error: %s. Retrying in %.1fs…",
                    exc,
                    wait,
                )
                last_exception = exc
                await asyncio.sleep(wait)

        # All retries exhausted.
        if isinstance(last_exception, RateLimitError):
            raise last_exception
        raise MonsterLabError(
            f"Request failed after {_MAX_RETRIES} attempts: {last_exception}"
        ) from last_exception

    # -- Public API methods ---------------------------------------------------

    async def validate_key(self, api_key: str | None = None) -> ValidationResult:
        """Validate an API key via **POST /api/validate** (public, no auth).

        Parameters
        ----------
        api_key:
            Key to validate.  Defaults to the key this client was
            initialised with.

        Returns
        -------
        ValidationResult
        """
        key = api_key or self._api_key
        logger.info("Validating API key %s…%s", key[:6], key[-4:])

        data = await self._request(
            "POST",
            "/api/validate",
            json_body={"apiKey": key},
            auth=False,
        )
        return ValidationResult(valid=bool(data.get("valid", False)))

    async def submit_clip(
        self,
        url: str,
        campaign_id: str | None = None,
        *,
        password: str | None = None,
        label: str | None = None,
        notes: str | None = None,
    ) -> Dict[str, Any]:
        """Submit a clip via **POST /api/clips/submit**.

        Parameters
        ----------
        url:
            Public URL of the clip (TikTok, Instagram, etc.).
        campaign_id:
            Optional campaign identifier (``camp_xxxxxx``).
        password:
            Optional password if the clip is private.
        label:
            Optional human-readable label for the submission.
        notes:
            Optional notes attached to the submission.

        Returns
        -------
        dict
            Raw JSON response from the API.

        Raises
        ------
        SubmissionError
            If the API explicitly rejects the submission.
        """
        payload: Dict[str, Any] = {
            "url": url,
        }
        if campaign_id is not None:
            payload["campaignId"] = campaign_id
        if password is not None:
            payload["password"] = password
        if label is not None:
            payload["label"] = label
        if notes is not None:
            payload["notes"] = notes

        logger.info("Submitting clip%s: %s", f" to campaign {campaign_id}" if campaign_id else "", url)

        data = await self._request("POST", "/api/clips/submit", json_body=payload)
        return data

    async def get_campaigns(self) -> Dict[str, Any]:
        """Fetch available campaigns via **GET /api/clips/campaigns**.

        Returns
        -------
        dict
            Raw JSON response from the API.
        """
        logger.info("Fetching campaigns…")
        data = await self._request("GET", "/api/clips/campaigns")
        return data

    async def get_account_info(self) -> Dict[str, Any]:
        """Fetch account information via **GET /api/account/info**.

        .. note:: This endpoint path is inferred and may change.

        Returns
        -------
        dict
            Raw JSON response.
        """
        logger.info("Fetching account info…")
        data = await self._request("GET", "/api/account/info")
        return data

    async def get_account_usage(self) -> Dict[str, Any]:
        """Fetch account usage via **GET /api/account/usage**.

        .. note:: This endpoint path is inferred and may change.

        Returns
        -------
        dict
            Raw JSON response.
        """
        logger.info("Fetching account usage…")
        data = await self._request("GET", "/api/account/usage")
        return data

    async def get_account_limits(self) -> Dict[str, Any]:
        """Fetch account rate/quota limits via **GET /api/account/limits**.

        .. note:: This endpoint path is inferred and may change.

        Returns
        -------
        dict
            Raw JSON response.
        """
        logger.info("Fetching account limits…")
        data = await self._request("GET", "/api/account/limits")
        return data


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _parse_retry_after(
    headers: aiohttp.typedefs.CIMultiDictProxy[str],
    attempt: int,
) -> float:
    """Determine how long to wait before retrying a 429 response.

    Checks the ``Retry-After`` header first; falls back to exponential
    backoff based on *attempt*.
    """
    raw = headers.get("Retry-After")
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            pass
    return _BACKOFF_BASE * (_BACKOFF_FACTOR ** (attempt - 1))
