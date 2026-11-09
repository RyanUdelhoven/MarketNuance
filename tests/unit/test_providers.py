import datetime as dt
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from marketnuance.http_client import ApiError
from marketnuance.providers import AlpacaClient, SecClient


class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class AlpacaClientTests(unittest.TestCase):
    def test_snapshots_batch_symbols_and_feed(self):
        http = FakeHttp({"AAPL": {"dailyBar": {"t": "latest"}}, "IGNORED": {}})
        client = AlpacaClient("key", "secret", feed="iex", http=http)

        result = client.snapshots(["AAPL", "MSFT"])

        self.assertEqual(list(result), ["AAPL"])
        self.assertEqual(http.calls[0][1]["params"], {"symbols": "AAPL,MSFT", "feed": "iex"})

    def test_assets_request_uses_documented_filters_and_credentials(self):
        http = FakeHttp([{"symbol": "AAPL"}])
        client = AlpacaClient("key", "secret", http=http)

        self.assertEqual(client.list_active_us_equities(), [{"symbol": "AAPL"}])
        _, request = http.calls[0]
        self.assertEqual(request["params"], {"status": "active", "asset_class": "us_equity"})
        self.assertEqual(request["headers"]["APCA-API-KEY-ID"], "key")
        self.assertEqual(request["headers"]["APCA-API-SECRET-KEY"], "secret")

    def test_bars_follow_pagination_and_merge_symbol_results(self):
        http = FakeHttp(
            {"bars": {"AAPL": [{"t": "first"}]}, "next_page_token": "next"},
            {"bars": {"AAPL": [{"t": "second"}], "MSFT": [{"t": "only"}]}},
        )
        client = AlpacaClient("key", "secret", feed="iex", http=http)
        start = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)

        bars = client.historical_daily_bars(["AAPL", "MSFT"], start, end)

        self.assertEqual([bar["t"] for bar in bars["AAPL"]], ["first", "second"])
        self.assertEqual(http.calls[1][1]["params"]["page_token"], "next")
        self.assertEqual(http.calls[0][1]["params"]["feed"], "iex")

    def test_bars_reject_repeated_pagination_token(self):
        http = FakeHttp(
            {"bars": {}, "next_page_token": "same"},
            {"bars": {}, "next_page_token": "same"},
        )
        client = AlpacaClient("key", "secret", http=http)
        moment = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)

        with self.assertRaisesRegex(ApiError, "repeated pagination token"):
            client.historical_daily_bars(["AAPL"], moment, moment)


class SecClientTests(unittest.TestCase):
    def test_current_facts_reuse_cache_when_no_new_annual_filing_exists(self):
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            {"form": "10-K", "filed": "2026-02-01"}
        ]}}}}}
        submissions = {"filings": {"recent": {"form": ["10-K"], "filingDate": ["2026-02-01"]}}}
        http = FakeHttp(facts, submissions)
        with tempfile.TemporaryDirectory() as directory:
            client = SecClient("Name name@example.com", directory, http=http, sleep=lambda _: None)
            client.company_facts("0000320193")
            result, downloaded = client.current_company_facts("0000320193")

        self.assertEqual(result, facts)
        self.assertFalse(downloaded)
        self.assertEqual(len(http.calls), 2)

    def test_ticker_map_normalizes_share_class_symbols(self):
        http = FakeHttp({"0": {"ticker": "BRK-B", "cik_str": 1067983}})
        with tempfile.TemporaryDirectory() as directory:
            client = SecClient("Name name@example.com", directory, http=http)
            self.assertEqual(client.ticker_map(), {"BRKB": "0001067983"})

    def test_company_facts_are_cached_after_one_request(self):
        payload = {"facts": {"us-gaap": {}}}
        http = FakeHttp(payload)
        pauses = []
        with tempfile.TemporaryDirectory() as directory:
            client = SecClient(
                "Name name@example.com",
                directory,
                http=http,
                sleep=pauses.append,
            )
            first = client.company_facts("0000320193")
            second = client.company_facts("0000320193")

            self.assertEqual(first, payload)
            self.assertEqual(second, payload)
            self.assertEqual(len(http.calls), 1)
            self.assertEqual(pauses, [0.22])

    def test_forced_company_facts_refresh_bypasses_valid_cache(self):
        first_payload = {"facts": {"us-gaap": {"first": {}}}}
        second_payload = {"facts": {"us-gaap": {"second": {}}}}
        http = FakeHttp(first_payload, second_payload)
        with tempfile.TemporaryDirectory() as directory:
            client = SecClient("Name name@example.com", directory, http=http, sleep=lambda _: None)
            client.company_facts("0000320193")
            result = client.company_facts("0000320193", force_refresh=True)

            self.assertEqual(result, second_payload)
            self.assertEqual(len(http.calls), 2)


if __name__ == "__main__":
    unittest.main()
