import sys
from pathlib import Path
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import (
    annual_facts, compute_stats, eligible_assets, load_env_file, normalize_criteria,
    passes_market, passes_sec, refresh, sec_metrics,
)


def fact(start, end, value, filed="2026-03-01", tag="", form="10-K"):
    return {"start": start, "end": end, "val": value, "filed": filed, "form": form, "fp": "FY"}


class DataIntegrityTests(unittest.TestCase):
    def test_market_criteria_validate_and_reject_missing_metrics(self):
        criteria = normalize_criteria({"minPrice": 5, "minVolume": 100})
        self.assertTrue(passes_market({"close": 10, "avg_volume_20": 200, "return_20_pct": ""}, criteria))
        criteria = normalize_criteria({"minReturn": 1})
        self.assertFalse(passes_market({"close": 10, "avg_volume_20": 200, "return_20_pct": ""}, criteria))
        with self.assertRaisesRegex(ValueError, "minPrice cannot exceed"):
            normalize_criteria({"minPrice": 20, "maxPrice": 10})

    def test_request_multiples_are_positive_and_normalized(self):
        criteria = normalize_criteria({"businessMultiple": 12.5, "bookValueMultiple": 2})
        self.assertEqual(criteria["businessMultiple"], 12.5)
        self.assertEqual(criteria["bookValueMultiple"], 2.0)
        with self.assertRaisesRegex(ValueError, "businessMultiple must be greater than zero"):
            normalize_criteria({"businessMultiple": 0})

    def test_market_only_refresh_does_not_require_or_construct_sec_client(self):
        row = {"symbol": "TEST", "name": "Test Inc", "asof": "2026-09-14", "close": 10,
               "avg_volume_20": 1000, "return_20_pct": 2, "high_52w": 12, "source": "Alpaca"}
        fake_alpaca = SimpleNamespace(feed="iex")
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"APCA_API_KEY_ID": "key", "APCA_API_SECRET_KEY": "secret"}, clear=True
        ), patch("app.AlpacaClient", return_value=fake_alpaca), patch(
            "app.SecClient", side_effect=AssertionError("SEC must be skipped")
        ), patch("app.universe", return_value=[("TEST", "Test Inc")]), patch(
            "app.market_rows", return_value=[row]
        ), patch("app.OUT", Path(directory) / "stocks.csv"):
            output, providers = refresh(SimpleNamespace(limit=1, symbols=None), criteria={"minPrice": 5})
        self.assertEqual([item["symbol"] for item in output], ["TEST"])
        self.assertFalse(providers["sec"]["checked"])

    def test_sec_checks_only_market_survivors(self):
        passing = {"symbol": "PASS", "name": "Pass Inc", "asof": "2026-09-14", "close": 20,
                   "avg_volume_20": 1000, "return_20_pct": 2, "high_52w": 22, "source": "Alpaca"}
        rejected = {**passing, "symbol": "FAIL", "name": "Fail Inc", "close": 2}
        facts = {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [fact("2025-01-01", "2025-12-31", 200_000_000)]}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [fact("2025-01-01", "2025-12-31", 3)]}},
        }}}
        fake_alpaca = SimpleNamespace(feed="iex")
        fake_sec = SimpleNamespace(
            ticker_map=lambda: {"PASS": "0000000001", "FAIL": "0000000002"},
            current_company_facts=lambda cik: (facts, False),
        )
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"APCA_API_KEY_ID": "key", "APCA_API_SECRET_KEY": "secret", "SEC_USER_AGENT": "Name name@example.com"},
            clear=True,
        ), patch("app.AlpacaClient", return_value=fake_alpaca), patch(
            "app.SecClient", return_value=fake_sec
        ), patch("app.universe", return_value=[("PASS", "Pass Inc"), ("FAIL", "Fail Inc")]), patch(
            "app.market_rows", return_value=[passing, rejected]
        ), patch("app.OUT", Path(directory) / "stocks.csv"):
            output, providers = refresh(
                SimpleNamespace(limit=2, symbols=None),
                criteria={"minPrice": 10, "minRevenue": 100, "businessMultiple": 20, "bookValueMultiple": 2},
            )
        self.assertEqual([item["symbol"] for item in output], ["PASS"])
        self.assertEqual(output[0]["eps_target_price"], 60)
        self.assertEqual(providers["sec"]["candidates"], 1)

    def test_env_file_loads_values_without_overriding_process_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "FROM_FILE=loaded\nEXISTING=file-value\nSEC_USER_AGENT='Name name@example.com'\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"EXISTING": "process-value"}, clear=True):
                load_env_file(env_path)
                self.assertEqual(os.environ["FROM_FILE"], "loaded")
                self.assertEqual(os.environ["EXISTING"], "process-value")
                self.assertEqual(os.environ["SEC_USER_AGENT"], "Name name@example.com")

    def test_short_price_history_leaves_derived_metrics_blank(self):
        bars = [{"t": "2026-09-12T00:00:00Z", "c": 10, "h": 11, "v": 100}]
        result = compute_stats("TEST", "Example", bars)
        self.assertEqual(result["avg_volume_20"], "")
        self.assertEqual(result["return_20_pct"], "")

    def test_full_price_history_uses_21_closes(self):
        bars = [{"t": f"2026-08-{i+1:02}T00:00:00Z", "c": 10 if i == 0 else 11,
                 "h": 12, "v": 100 + i} for i in range(21)]
        result = compute_stats("TEST", "Example", bars)
        self.assertEqual(result["return_20_pct"], 10.0)
        self.assertEqual(result["avg_volume_20"], 110)

    def test_asset_filter_rejects_etf_and_inactive(self):
        assets = [
            {"symbol": "GOOD", "name": "Good Inc", "status": "active", "class": "us_equity"},
            {"symbol": "FUND", "name": "Example Index ETF", "status": "active", "class": "us_equity"},
            {"symbol": "DEAD", "name": "Old Inc", "status": "inactive", "class": "us_equity"},
        ]
        self.assertEqual(list(eligible_assets(assets)), [("GOOD", "Good Inc")])

    def test_sec_metrics_match_annual_period_and_use_restated_fact(self):
        current = fact("2025-01-01", "2025-12-31", 120_000_000)
        restated = fact("2025-01-01", "2025-12-31", 130_000_000, "2026-04-01")
        prior = fact("2024-01-01", "2024-12-31", 100_000_000, "2025-03-01")
        quarterly = fact("2025-10-01", "2025-12-31", 90_000_000, "2026-05-01")
        matching_income = fact("2025-01-01", "2025-12-31", 13_000_000)
        wrong_income = fact("2024-01-01", "2024-12-31", 99_000_000)
        data = {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [prior, current, restated, quarterly]}},
            "NetIncomeLoss": {"units": {"USD": [wrong_income, matching_income]}}
        }}}
        metrics = sec_metrics(data)
        self.assertEqual(metrics["revenue_fy"], 130)
        self.assertEqual(metrics["revenue_growth_pct"], 30)
        self.assertEqual(metrics["net_margin_pct"], 10)
        self.assertEqual(metrics["filing_date"], "2026-04-01")

    def test_sec_missing_or_nonannual_never_becomes_zero(self):
        data = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            fact("2025-10-01", "2025-12-31", 1_000_000)]}}}}}
        self.assertEqual(sec_metrics(data)["revenue_fy"], "")
        self.assertEqual(annual_facts(data, ("Revenues",)), [])

    def test_valuation_targets_use_per_share_values_and_correct_book_formula(self):
        period = ("2025-01-01", "2025-12-31")
        instant = {"end": period[1], "val": 2_000_000_000, "filed": "2026-03-01", "form": "10-K", "fp": "FY"}
        shares = {**instant, "val": 100_000_000}
        data = {"facts": {
            "us-gaap": {
                "EarningsPerShareDiluted": {"units": {"USD/shares": [fact(*period, 3)]}},
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [fact(*period, 300_000_000)]}},
                "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [fact(*period, 100_000_000)]}},
                "StockholdersEquity": {"units": {"USD": [instant]}},
            },
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [shares]}}},
        }}

        metrics = sec_metrics(data, current_price=40, business_multiple=15, book_value_multiple=1.5)

        self.assertEqual(metrics["eps_target_price"], 45)
        self.assertEqual(metrics["operating_cashflow_per_share"], 3)
        self.assertEqual(metrics["cashflow_target_price"], 45)
        self.assertEqual(metrics["book_value_per_share"], 20)
        self.assertEqual(metrics["book_value_target_price"], 30)
        self.assertEqual(metrics["buy_signal_count"], 2)
        criteria = normalize_criteria({"minEpsTarget": 44, "minBuySignals": 2})
        self.assertTrue(passes_sec({**metrics, "revenue_fy": "", "revenue_growth_pct": "", "net_margin_pct": ""}, criteria))


if __name__ == "__main__":
    unittest.main()
