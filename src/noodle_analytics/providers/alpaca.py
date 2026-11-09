"""Alpaca asset-directory and historical market-data client."""

from datetime import datetime

from noodle_analytics.http_client import ApiError, JsonHttpClient


class AlpacaClient:
    ASSETS_URL = "https://paper-api.alpaca.markets/v2/assets"
    BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
    SNAPSHOTS_URL = "https://data.alpaca.markets/v2/stocks/snapshots"
    ALLOWED_FEEDS = {"iex", "sip"}

    def __init__(self, key, secret, *, feed="iex", http=None):
        if not key or not secret:
            raise ValueError("Alpaca API credentials are required.")
        if feed not in self.ALLOWED_FEEDS:
            raise ValueError(f"ALPACA_DATA_FEED must be one of: {', '.join(sorted(self.ALLOWED_FEEDS))}.")
        self.feed = feed
        self.http = http or JsonHttpClient()
        self.headers = {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
        }

    @property
    def source_label(self):
        return f"Alpaca historical {self.feed.upper()}"

    def list_active_us_equities(self):
        payload = self.http.get(
            self.ASSETS_URL,
            headers=self.headers,
            params={"status": "active", "asset_class": "us_equity"},
        )
        if not isinstance(payload, list):
            raise ApiError("Alpaca assets response must be a list.")
        return payload

    def historical_daily_bars(self, symbols, start, end):
        if not symbols:
            return {}
        params = {
            "symbols": ",".join(symbols),
            "timeframe": "1Day",
            "start": self._timestamp(start),
            "end": self._timestamp(end),
            "feed": self.feed,
            "limit": "10000",
            "sort": "asc",
        }
        result = {symbol: [] for symbol in symbols}
        seen_tokens = set()
        for _ in range(1000):
            payload = self.http.get(self.BARS_URL, headers=self.headers, params=params)
            if not isinstance(payload, dict) or not isinstance(payload.get("bars", {}), dict):
                raise ApiError("Alpaca bars response has an invalid shape.")
            for symbol, bars in payload.get("bars", {}).items():
                if symbol in result:
                    if not isinstance(bars, list):
                        raise ApiError(f"Alpaca bars for {symbol} must be a list.")
                    result[symbol].extend(bars)
            token = payload.get("next_page_token")
            if not token:
                return result
            if token in seen_tokens:
                raise ApiError("Alpaca returned a repeated pagination token.")
            seen_tokens.add(token)
            params["page_token"] = token
        raise ApiError("Alpaca bars pagination exceeded the safety limit.")

    def snapshots(self, symbols):
        """Return Alpaca's newest consolidated snapshot for each requested symbol."""
        if not symbols:
            return {}
        payload = self.http.get(
            self.SNAPSHOTS_URL,
            headers=self.headers,
            params={"symbols": ",".join(symbols), "feed": self.feed},
        )
        if not isinstance(payload, dict):
            raise ApiError("Alpaca snapshots response must be an object.")
        return {symbol: value for symbol, value in payload.items() if symbol in symbols and isinstance(value, dict)}

    @staticmethod
    def _timestamp(value):
        if not isinstance(value, datetime):
            raise TypeError("Bar range values must be datetime objects.")
        return value.isoformat().replace("+00:00", "Z")
