"""WhatsApp Integration Gateway HTTP Client.

Reusable client module with:
- Bearer token authentication
- JSON serialization/parsing
- Configurable timeout (15-30s)
- Typed error hierarchy
- Specific handling for 401, 403, 422, 429 (Retry-After), 5xx backoff
- Request ID tracing and secure logging (never logs API keys)
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .config import settings

logger = logging.getLogger("nmhirex.gateway")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


# ============================================================
# TYPED GATEWAY EXCEPTIONS
# ============================================================
class GatewayError(Exception):
    """Base exception for all WhatsApp Gateway communication failures."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        request_id: str | None = None,
        error_code: str | None = None,
        raw_body: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
        self.error_code = error_code
        self.raw_body = raw_body

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": False,
            "requestId": self.request_id,
            "error": {
                "code": self.error_code or f"HTTP_{self.status_code}",
                "message": self.message,
            },
        }


class GatewayAuthError(GatewayError):
    """401: Invalid, revoked, or expired API key."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, status_code=401, **kwargs)


class GatewayForbiddenError(GatewayError):
    """403: Missing required scope or IP address not allowed."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, status_code=403, **kwargs)


class GatewayValidationError(GatewayError):
    """422: Payload validation error."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, status_code=422, **kwargs)


class GatewayRateLimitError(GatewayError):
    """429: Rate limit exceeded after retries exhausted."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, status_code=429, **kwargs)


class GatewayServerError(GatewayError):
    """5xx / 503: Upstream gateway server error."""
    def __init__(self, message: str, status_code: int = 500, **kwargs):
        super().__init__(message, status_code=status_code, **kwargs)


class GatewayConnectionError(GatewayError):
    """Network connection timeout or failure reaching gateway."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, status_code=504, **kwargs)


# ============================================================
# GATEWAY CLIENT CLASS
# ============================================================
class WhatsAppGatewayClient:
    """Client for making POST requests to the WhatsApp Integration Gateway."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
    ):
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        url = (
            self._base_url
            or os.getenv("NMHIREX_GATEWAY_URL")
            or getattr(settings, "NMHIREX_GATEWAY_URL", "")
            or "https://nmve.io/whatsapp"
        )
        return url.rstrip("/")

    @property
    def api_key(self) -> str:
        return (
            self._api_key
            or os.getenv("NMHIREX_API_KEY")
            or getattr(settings, "NMHIREX_API_KEY", "")
            or getattr(settings, "WHATSAPP_API_KEY", "")
        )

    @property
    def timeout(self) -> int:
        if self._timeout is not None:
            return self._timeout
        val = getattr(settings, "NMHIREX_GATEWAY_TIMEOUT_SECONDS", 25)
        # Constrain timeout to between 15 and 30 seconds
        return max(15, min(30, int(val)))

    def _parse_error_body(
        self, raw_body: str
    ) -> tuple[str, str | None, str | None]:
        """Extracts (message, error_code, request_id) from error response body."""
        if not raw_body:
            return "Empty error response from gateway", None, None

        try:
            data = json.loads(raw_body)
            if isinstance(data, dict):
                # Shape 1: { success: false, requestId, error: { code, message } }
                req_id = data.get("requestId") or data.get("request_id")
                err_obj = data.get("error")
                if isinstance(err_obj, dict):
                    msg = err_obj.get("message") or err_obj.get("code") or raw_body
                    code = err_obj.get("code")
                    return str(msg), code, req_id

                # Shape 2: { statusCode, message, requestId }
                msg = data.get("message") or data.get("detail")
                if msg:
                    return str(msg), data.get("code"), req_id

                return raw_body, None, req_id
        except Exception:
            pass

        return raw_body, None, None

    def post(
        self,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        is_write: bool = False,
    ) -> dict[str, Any]:
        """Execute POST request to WhatsApp Gateway with error handling and retries.

        Args:
            endpoint: API path (e.g. '/api/integrations/whatsapp/raw/schedules')
            payload: JSON serializable request body
            is_write: If True, disables auto-retries on 5xx to prevent duplicate mutations.

        Returns:
            dict containing the parsed JSON response.

        Raises:
            GatewayAuthError (401)
            GatewayForbiddenError (403)
            GatewayValidationError (422)
            GatewayRateLimitError (429)
            GatewayServerError (5xx)
            GatewayConnectionError (Network/timeout)
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
                "NMHIREX_API_KEY is not configured. Set it in .env or environment.",
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

        # Retry limits
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

                # 429 Rate Limiting (retry up to 3 times after Retry-After)
                if err.code == 429:
                    if rate_limit_attempts < max_rate_limit_retries:
                        rate_limit_attempts += 1
                        retry_after_str = headers_map.get("retry-after")
                        try:
                            retry_after = float(retry_after_str) if retry_after_str else (1.5 * rate_limit_attempts)
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

                # 5xx / 503 Server Errors
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

                    # For write calls, never auto-retry on 5xx because DB commit may have succeeded
                    raise GatewayServerError(
                        f"Gateway server error ({err.code}): {msg}",
                        status_code=err.code,
                        request_id=request_id,
                        error_code=err_code,
                        raw_body=err_raw,
                    )

                # 401 Invalid/expired/revoked key
                if err.code == 401:
                    raise GatewayAuthError(
                        f"Unauthorized (401): {msg}",
                        request_id=request_id,
                        error_code=err_code,
                        raw_body=err_raw,
                    )

                # 403 Forbidden / Missing scope / IP not allowed
                if err.code == 403:
                    raise GatewayForbiddenError(
                        f"Forbidden (403): {msg}",
                        request_id=request_id,
                        error_code=err_code,
                        raw_body=err_raw,
                    )

                # 422 Validation error
                if err.code == 422:
                    raise GatewayValidationError(
                        f"Validation error (422): {msg}",
                        request_id=request_id,
                        error_code=err_code,
                        raw_body=err_raw,
                    )

                # Other HTTP errors
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


# Export singleton default client
default_gateway_client = WhatsAppGatewayClient()

