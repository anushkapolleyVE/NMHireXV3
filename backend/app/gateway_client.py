"""WhatsApp Integration Gateway HTTP Client.

This module provides a production-grade, hardened HTTP client for interacting with
the external Virtual Employee / NMVE WhatsApp Integration Gateway (default: https://nmve.io/whatsapp).

Core Responsibilities:
1. Low-level HTTP Transport: Handles POST requests using Python's standard `urllib.request`.
2. Strict API Key Isolation: Exclusively loads Key 2 (`NMHIREX_GATEWAY_API_KEY`) to prevent 403 Forbidden errors.
3. Resilient Error Handling & Retry Engine:
   - Automatically handles HTTP 429 (Rate Limit) by respecting `Retry-After` headers (up to 3 retries).
   - Automatically retries idempotent read requests on HTTP 5xx / 503 upstream server failures.
   - Prevents duplicate candidate mutations by disabling retries for write operations (`is_write=True`).
4. Typed Exception Hierarchy: Translates raw HTTP status codes and gateway JSON payloads into typed exceptions.
5. Request Tracing & Security: Extracts `x-request-id` headers for tracing and guarantees API keys are never logged.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .config import settings

# Configure dedicated logger for gateway communication
logger = logging.getLogger("nmhirex.gateway")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


# ============================================================
# TYPED GATEWAY EXCEPTIONS
# ============================================================
class GatewayError(Exception):
    """Base exception for all WhatsApp Gateway communication failures.

    Stores detailed context about the HTTP error including HTTP status code,
    upstream request ID (for log correlation), error code, and raw body.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        request_id: str | None = None,
        error_code: str | None = None,
        raw_body: str | None = None,
    ):
        """Initialize the base GatewayError.

        Args:
            message (str): Human-readable error description.
            status_code (int): HTTP status code returned by the gateway (default: 500).
            request_id (str | None): Unique request ID from gateway headers or body for audit tracing.
            error_code (str | None): Upstream machine-readable error string (e.g. 'INVALID_PAYLOAD').
            raw_body (str | None): Raw, unparsed response body string for forensic debugging.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
        self.error_code = error_code
        self.raw_body = raw_body

    def to_dict(self) -> dict[str, Any]:
        """Convert the gateway exception into a standardized dictionary.

        Useful for returning uniform error JSON payloads in FastAPI route responses.

        Returns:
            dict[str, Any]: Formatted dictionary with success status, requestId, and error details.
        """
        return {
            "success": False,
            "requestId": self.request_id,
            "error": {
                "code": self.error_code or f"HTTP_{self.status_code}",
                "message": self.message,
            },
        }


class GatewayAuthError(GatewayError):
    """Raised on HTTP 401: Unauthorized.

    Indicates an invalid, expired, or missing Gateway API key (Key 2).
    Check NMHIREX_GATEWAY_API_KEY in the environment or configuration.
    """

    def __init__(self, message: str, **kwargs):
        """Initialize GatewayAuthError with default status code 401."""
        super().__init__(message, status_code=401, **kwargs)


class GatewayForbiddenError(GatewayError):
    """Raised on HTTP 403: Forbidden.

    Indicates that the API key does not have the necessary scope (e.g., missing candidates:write
    or interviews:read), or the outbound server's IP address is not whitelisted by the gateway.
    """

    def __init__(self, message: str, **kwargs):
        """Initialize GatewayForbiddenError with default status code 403."""
        super().__init__(message, status_code=403, **kwargs)


class GatewayValidationError(GatewayError):
    """Raised on HTTP 422: Unprocessable Entity.

    Indicates that the JSON payload failed gateway schema validation (e.g., invalid phone format,
    missing required fields like interview_date/time, or unparseable candidate data).
    """

    def __init__(self, message: str, **kwargs):
        """Initialize GatewayValidationError with default status code 422."""
        super().__init__(message, status_code=422, **kwargs)


class GatewayRateLimitError(GatewayError):
    """Raised on HTTP 429: Too Many Requests.

    Indicates that the gateway's rate limit was exceeded and all automated retry attempts
    (respecting the Retry-After header) have been exhausted.
    """

    def __init__(self, message: str, **kwargs):
        """Initialize GatewayRateLimitError with default status code 429."""
        super().__init__(message, status_code=429, **kwargs)


class GatewayServerError(GatewayError):
    """Raised on HTTP 5xx / 503: Gateway Server Errors.

    Indicates an internal server error or temporary outage in the external gateway service.
    """

    def __init__(self, message: str, status_code: int = 500, **kwargs):
        """Initialize GatewayServerError with status code 500-599."""
        super().__init__(message, status_code=status_code, **kwargs)


class GatewayConnectionError(GatewayError):
    """Raised on network-level drops, DNS resolution failures, or gateway timeouts.

    Maps to HTTP 504 Gateway Timeout semantics when the remote host is unreachable.
    """

    def __init__(self, message: str, **kwargs):
        """Initialize GatewayConnectionError with status code 504."""
        super().__init__(message, status_code=504, **kwargs)


# ============================================================
# GATEWAY CLIENT CLASS
# ============================================================
class WhatsAppGatewayClient:
    """Client for making authenticated POST requests to the WhatsApp Integration Gateway.

    Encapsulates connection configuration, bearer token authentication (Key 2),
    timeout bounding, automatic retry logic, and JSON parsing.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
    ):
        """Initialize the WhatsAppGatewayClient instance.

        Args:
            base_url (str | None): Base URL of the gateway. If None, loaded from env/settings.
            api_key (str | None): Gateway API Key (Key 2). If None, loaded from env/settings.
            timeout (int | None): Request timeout in seconds. If None, bounded default is used.
        """
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        """Resolve the effective Gateway Base URL.

        Resolution hierarchy:
        1. Explicit `base_url` passed to constructor.
        2. Environment variable `NMHIREX_GATEWAY_URL`.
        3. Application settings `settings.NMHIREX_GATEWAY_URL`.
        4. Hardcoded production fallback: `https://nmve.io/whatsapp`.

        Returns:
            str: Normalized base URL without trailing slashes.
        """
        url = (
            self._base_url
            or os.getenv("NMHIREX_GATEWAY_URL")
            or getattr(settings, "NMHIREX_GATEWAY_URL", "")
            or "https://nmve.io/whatsapp"
        )
        return url.rstrip("/")

    @property
    def api_key(self) -> str:
        """Resolve the effective Gateway API Key (STRICTLY Key 2).

        Resolution hierarchy:
        1. Explicit `api_key` passed to constructor.
        2. Environment variable `NMHIREX_GATEWAY_API_KEY`.
        3. Application settings `settings.NMHIREX_GATEWAY_API_KEY`.
        4. Legacy environment fallback `NMHIREX_API_KEY`.

        Security & Scoping Note:
        This property STRICTLY avoids falling back to Key 1 (`WHATSAPP_MESSAGE_API_KEY`).
        Key 1 is scoped only for direct candidate messaging, whereas Key 2 has the required
        gateway scopes (`candidates:write`, `interviews:read`) to avoid 403 Forbidden errors.

        Returns:
            str: Resolved Gateway API Key.
        """
        return (
            self._api_key
            or os.getenv("NMHIREX_GATEWAY_API_KEY")
            or getattr(settings, "NMHIREX_GATEWAY_API_KEY", "")
            or os.getenv("NMHIREX_API_KEY")
            or getattr(settings, "NMHIREX_API_KEY", "")
        )

    @property
    def timeout(self) -> int:
        """Resolve the HTTP request timeout clamped between 15 and 30 seconds.

        Guarantees that external gateway latency spikes do not block ASGI threads
        indefinitely while giving slow upstream databases sufficient time to respond.

        Returns:
            int: Timeout value in seconds (clamped to range [15, 30]).
        """
        if self._timeout is not None:
            return self._timeout
        val = getattr(settings, "NMHIREX_GATEWAY_TIMEOUT_SECONDS", 25)
        return max(15, min(30, int(val)))

    def _parse_error_body(
        self, raw_body: str
    ) -> tuple[str, str | None, str | None]:
        """Extract error message, error code, and request ID from raw upstream response.

        The external gateway can return diverse error payloads depending on the failure layer:
        - Shape 1: `{"success": false, "requestId": "...", "error": {"code": "...", "message": "..."}}`
        - Shape 2: `{"statusCode": 400, "message": "...", "requestId": "..."}`
        - Shape 3: Plain text HTML/string errors from reverse proxies.

        Args:
            raw_body (str): Raw response body string returned by the gateway.

        Returns:
            tuple[str, str | None, str | None]: (error_message, error_code, request_id)
        """
        if not raw_body:
            return "Empty error response from gateway", None, None

        try:
            data = json.loads(raw_body)
            if isinstance(data, dict):
                # Shape 1: Nested error object
                req_id = data.get("requestId") or data.get("request_id")
                err_obj = data.get("error")
                if isinstance(err_obj, dict):
                    msg = err_obj.get("message") or err_obj.get("code") or raw_body
                    code = err_obj.get("code")
                    return str(msg), code, req_id

                # Shape 2: Flat message/detail structure
                msg = data.get("message") or data.get("detail")
                if msg:
                    return str(msg), data.get("code"), req_id

                return raw_body, None, req_id
        except Exception:
            # Not valid JSON; fall back to returning raw string content
            pass

        return raw_body, None, None

    def post(
        self,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        is_write: bool = False,
    ) -> dict[str, Any]:
        """Execute an authenticated HTTP POST request to the WhatsApp Gateway.

        Handles:
        1. Base URL construction and header preparation (Bearer Key 2).
        2. 429 Rate Limiting with exponential backoff & Retry-After header parsing (up to 3 retries).
        3. 5xx Server Error handling with exponential backoff for read queries.
        4. Write idempotency protection: disables auto-retries on 5xx if `is_write=True`.
        5. Translation of HTTP error codes (401, 403, 422, 429, 5xx) into typed GatewayError exceptions.

        Args:
            endpoint (str): Gateway API path (e.g. '/api/integrations/whatsapp/raw/schedules').
            payload (dict[str, Any] | None): JSON serializable dictionary for request body.
            is_write (bool): If True, indicates state mutation (e.g. add-candidate) and prevents
                             auto-retrying 5xx errors to prevent duplicate candidate records.

        Returns:
            dict[str, Any]: Parsed JSON response dictionary from the gateway.

        Raises:
            GatewayAuthError: If authentication fails (401) or credentials are missing.
            GatewayForbiddenError: If key lacks permissions or IP is blocked (403).
            GatewayValidationError: If payload fails validation schema (422).
            GatewayRateLimitError: If rate limit exceeded and retries exhausted (429).
            GatewayServerError: If upstream service fails with 5xx.
            GatewayConnectionError: If network connection drops or times out.
            GatewayError: For any other unhandled HTTP errors.
        """
        base = self.base_url
        if not base:
            raise GatewayAuthError(
                "NMHIREX_GATEWAY_URL is not configured. Set it in .env or environment.",
                request_id=None,
            )

        key = self.api_key
        if not key:
            raise GatewayAuthError(
                "NMHIREX_GATEWAY_API_KEY (or NMHIREX_API_KEY) is not configured. Set it in .env or environment.",
                request_id=None,
            )

        url = f"{base}/{endpoint.lstrip('/')}"
        data = json.dumps(payload or {}).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "NM-HireX/1.0",
        }

        # Maximum retry attempt limits
        max_rate_limit_retries = 3
        max_server_retries = 0 if is_write else 2

        rate_limit_attempts = 0
        server_attempts = 0

        while True:
            request = urllib.request.Request(
                url,
                data=data,
                headers=headers,
                method="POST",
            )

            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw_res = response.read().decode("utf-8", errors="replace")
                    headers_map = dict(response.headers)
                    request_id = (
                        headers_map.get("x-request-id")
                        or headers_map.get("request-id")
                    )

                    parsed: dict[str, Any] = {}
                    if raw_res.strip():
                        try:
                            parsed = json.loads(raw_res)
                        except json.JSONDecodeError:
                            parsed = {"raw": raw_res}

                    if isinstance(parsed, dict) and not request_id:
                        request_id = parsed.get("requestId") or parsed.get("request_id")

                    logger.info(
                        "Gateway POST %s succeeded with status %s (requestId: %s)",
                        endpoint,
                        response.status,
                        request_id or "N/A",
                    )
                    return parsed

            except urllib.error.HTTPError as err:
                headers_map = dict(err.headers)
                req_id_header = (
                    headers_map.get("x-request-id")
                    or headers_map.get("request-id")
                )

                try:
                    err_raw = err.read().decode("utf-8", errors="replace")
                except Exception:
                    err_raw = ""

                msg, err_code, req_id_body = self._parse_error_body(err_raw)
                request_id = req_id_header or req_id_body or "N/A"

                logger.warning(
                    "Gateway HTTP %d on POST %s (requestId: %s): %s",
                    err.code,
                    endpoint,
                    request_id,
                    msg,
                )

                # 429 Rate Limiting: Backoff and retry up to max_rate_limit_retries
                if err.code == 429:
                    if rate_limit_attempts < max_rate_limit_retries:
                        rate_limit_attempts += 1
                        retry_after_str = headers_map.get("retry-after")
                        try:
                            retry_after = (
                                float(retry_after_str)
                                if retry_after_str
                                else (1.5 * rate_limit_attempts)
                            )
                        except ValueError:
                            retry_after = 2.0 * rate_limit_attempts

                        logger.warning(
                            "Rate limited (429) on %s (requestId: %s). Waiting %.2f s (attempt %d/%d)...",
                            endpoint,
                            request_id,
                            retry_after,
                            rate_limit_attempts,
                            max_rate_limit_retries,
                        )
                        time.sleep(retry_after)
                        continue

                    raise GatewayRateLimitError(
                        f"Rate limit exceeded (429): {msg}",
                        request_id=request_id,
                        error_code=err_code,
                        raw_body=err_raw,
                    )

                # 5xx / 503 Server Errors: Retry only for idempotent read calls
                if 500 <= err.code <= 599:
                    if not is_write and server_attempts < max_server_retries:
                        server_attempts += 1
                        backoff = 1.0 * (2 ** server_attempts)
                        logger.warning(
                            "Server error (%d) on %s (requestId: %s). Retrying in %.2f s (attempt %d/%d)...",
                            err.code,
                            endpoint,
                            request_id,
                            backoff,
                            server_attempts,
                            max_server_retries,
                        )
                        time.sleep(backoff)
                        continue

                    # For write calls, never auto-retry on 5xx because the DB transaction may have succeeded upstream
                    raise GatewayServerError(
                        f"Gateway server error ({err.code}): {msg}",
                        status_code=err.code,
                        request_id=request_id,
                        error_code=err_code,
                        raw_body=err_raw,
                    )

                # 401 Unauthorized: Invalid, expired, or revoked API key
                if err.code == 401:
                    raise GatewayAuthError(
                        f"Unauthorized (401): {msg}",
                        request_id=request_id,
                        error_code=err_code,
                        raw_body=err_raw,
                    )

                # 403 Forbidden: Missing required scope or disallowed IP
                if err.code == 403:
                    raise GatewayForbiddenError(
                        f"Forbidden (403): {msg}",
                        request_id=request_id,
                        error_code=err_code,
                        raw_body=err_raw,
                    )

                # 422 Validation Error: Payload syntax or field constraint violation
                if err.code == 422:
                    raise GatewayValidationError(
                        f"Validation error (422): {msg}",
                        request_id=request_id,
                        error_code=err_code,
                        raw_body=err_raw,
                    )

                # Other HTTP status errors
                raise GatewayError(
                    f"Gateway returned HTTP {err.code}: {msg}",
                    status_code=err.code,
                    request_id=request_id,
                    error_code=err_code,
                    raw_body=err_raw,
                )

            except urllib.error.URLError as err:
                logger.error(
                    "Network error connecting to Gateway %s: %s",
                    endpoint,
                    err.reason,
                )
                if not is_write and server_attempts < max_server_retries:
                    server_attempts += 1
                    backoff = 1.5 * server_attempts
                    time.sleep(backoff)
                    continue

                raise GatewayConnectionError(
                    f"Could not connect to WhatsApp Gateway at {url}: {err.reason}",
                    request_id=None,
                )


# Export singleton default client for shared application use
default_gateway_client = WhatsAppGatewayClient()
