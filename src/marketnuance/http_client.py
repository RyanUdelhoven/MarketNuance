"""Small resilient JSON HTTP client built on the Python standard library."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen


class ApiError(RuntimeError):
    """Raised when a provider request cannot return valid JSON."""


class JsonHttpClient:
    def __init__(self, user_agent="MarketNuance/0.1", attempts=4, timeout=45, sleep=time.sleep):
        self.user_agent = user_agent
        self.attempts = attempts
        self.timeout = timeout
        self.sleep = sleep

    @staticmethod
    def _with_params(url, params):
        if not params:
            return url
        scheme, netloc, path, query, fragment = urlsplit(url)
        merged = [*parse_qsl(query, keep_blank_values=True), *params.items()]
        return urlunsplit((scheme, netloc, path, urlencode(merged), fragment))

    def get(self, url, *, headers=None, params=None):
        request_url = self._with_params(url, params)
        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
                **(headers or {}),
            },
        )
        for attempt in range(self.attempts):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = response.read().decode("utf-8-sig")
                try:
                    return json.loads(payload)
                except json.JSONDecodeError as exc:
                    raise ApiError(f"Invalid JSON from {urlsplit(url).netloc}.") from exc
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if not retryable or attempt == self.attempts - 1:
                    raise ApiError(
                        f"Provider request failed: HTTP {exc.code} ({urlsplit(url).netloc})."
                    ) from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                self.sleep(min(delay, 30))
            except (URLError, TimeoutError) as exc:
                if attempt == self.attempts - 1:
                    reason = getattr(exc, "reason", str(exc))
                    raise ApiError(f"Could not reach {urlsplit(url).netloc}: {reason}.") from exc
                self.sleep(2**attempt)

