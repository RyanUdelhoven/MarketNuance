#!/usr/bin/env python3
"""Local daily stock discovery; standard-library-only."""
import argparse
import csv
import datetime as dt
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import sys
import threading
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from marketnuance.http_client import ApiError
from marketnuance.providers import AlpacaClient, SecClient

FRONTEND = ROOT / "frontend" / "dist"
DATA = ROOT / "data"
OUT = DATA / "snapshots" / "stocks.csv"
SEC_CACHE = DATA / "cache" / "sec"
ALPACA_CACHE = DATA / "cache" / "alpaca"
HEADERS = [
    "symbol", "name", "asof", "close", "avg_volume_20", "return_20_pct", "high_52w",
    "cik", "revenue_fy", "revenue_growth_pct", "net_margin_pct", "eps_diluted",
    "operating_cashflow_fy", "operating_cashflow_per_share", "book_value_per_share",
    "business_multiple", "book_value_multiple", "eps_target_price", "cashflow_target_price",
    "book_value_target_price", "eps_signal", "cashflow_signal", "book_value_signal",
    "buy_signal_count", "filing_date", "source",
]
DEMO = [
    ("ALFA", "Example Alpha", 51.20, 2500000, 8.2, 55.0),
    ("BETA", "Example Beta", 18.80, 420000, -2.1, 31.0),
    ("GAMA", "Example Gamma", 112.40, 1800000, 13.3, 116.0),
    ("DLTA", "Example Delta", 7.90, 72000, 1.5, 12.0),
    ("EPSI", "Example Epsilon", 76.10, 930000, -8.7, 125.0),
    ("ZETA", "Example Zeta", 29.00, 3100000, 4.4, 30.0),
]


def load_env_file(path):
    """Load simple KEY=VALUE entries without replacing existing environment values."""
    if not path.exists():
        return
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise RuntimeError(f"Invalid .env entry on line {line_number}.")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def eligible_assets(assets):
    for asset in assets:
        symbol, name = asset.get("symbol", ""), asset.get("name", "")
        if asset.get("status") != "active" or asset.get("class") != "us_equity":
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
            continue
        # Alpaca calls ETFs us_equity; this is a best-effort name filter.
        if re.search(r"\b(etf|etn|fund|trust|preferred|warrants?|depositary|units?|rights?|notes?|bonds?|debentures?)\b", name, re.I):
            continue
        yield symbol, name


def universe(limit, symbols, alpaca):
    ALPACA_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = ALPACA_CACHE / "assets.json"
    assets = None
    if cache_path.exists() and dt.datetime.now().timestamp() - cache_path.stat().st_mtime < 86400:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, list):
                assets = cached
        except (OSError, json.JSONDecodeError):
            pass
    if assets is None:
        assets = alpaca.list_active_us_equities()
        temporary = cache_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(assets), encoding="utf-8")
        temporary.replace(cache_path)
    by_symbol = dict(eligible_assets(assets))
    requested = set(symbols) if symbols else None
    if requested:
        absent = requested - by_symbol.keys()
        if absent:
            print("Skipped symbols absent from eligible Alpaca assets:", ", ".join(sorted(absent)))
        by_symbol = {s: n for s, n in by_symbol.items() if s in requested}
    results = sorted(by_symbol.items())
    return results[:limit] if limit else results


def annual_facts(facts, tags, unit="USD", taxonomy="us-gaap"):
    concepts = facts.get("facts", {}).get(taxonomy, {})
    for tag in tags:
        entries = concepts.get(tag, {}).get("units", {}).get(unit, [])
        annual = [e for e in entries if e.get("form") in ("10-K", "10-K/A") and e.get("fp") == "FY"
                  and e.get("start") and e.get("end") and e.get("filed") and isinstance(e.get("val"), (int, float))
                  and 330 <= (dt.date.fromisoformat(e["end"]) - dt.date.fromisoformat(e["start"])).days <= 380]
        if annual:
            unique = {}
            for e in annual:
                period = (e["start"], e["end"])
                if period not in unique or e["filed"] > unique[period]["filed"]:
                    unique[period] = e
            return sorted(unique.values(), key=lambda e: (e["end"], e["filed"]), reverse=True)
    return []


def instant_facts(facts, sources):
    """Return the newest restated 10-K instant facts from ordered taxonomy/tag/unit sources."""
    for taxonomy, tag, unit in sources:
        entries = facts.get("facts", {}).get(taxonomy, {}).get(tag, {}).get("units", {}).get(unit, [])
        annual = [e for e in entries if e.get("form") in ("10-K", "10-K/A") and e.get("fp") == "FY"
                  and e.get("end") and e.get("filed") and isinstance(e.get("val"), (int, float))]
        if annual:
            unique = {}
            for entry in annual:
                if entry["end"] not in unique or entry["filed"] > unique[entry["end"]]["filed"]:
                    unique[entry["end"]] = entry
            return sorted(unique.values(), key=lambda e: (e["end"], e["filed"]), reverse=True)
    return []


def sec_metrics(facts, *, current_price=None, business_multiple=15.0, book_value_multiple=1.5):
    revenue = annual_facts(facts, ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"))
    earnings = annual_facts(facts, ("NetIncomeLoss", "ProfitLoss"))
    eps = annual_facts(
        facts,
        ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"),
        unit="USD/shares",
    )
    cashflow = annual_facts(facts, ("NetCashProvidedByUsedInOperatingActivities",))
    diluted_shares = annual_facts(
        facts,
        ("WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"),
        unit="shares",
    )
    equity = instant_facts(facts, (
        ("us-gaap", "StockholdersEquity", "USD"),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "USD"),
    ))
    shares_outstanding = instant_facts(facts, (
        ("us-gaap", "CommonStockSharesOutstanding", "shares"),
        ("dei", "EntityCommonStockSharesOutstanding", "shares"),
    ))
    result = {
        "revenue_fy": "", "revenue_growth_pct": "", "net_margin_pct": "", "eps_diluted": "",
        "operating_cashflow_fy": "", "operating_cashflow_per_share": "", "book_value_per_share": "",
        "business_multiple": business_multiple, "book_value_multiple": book_value_multiple,
        "eps_target_price": "", "cashflow_target_price": "", "book_value_target_price": "",
        "eps_signal": "", "cashflow_signal": "", "book_value_signal": "", "buy_signal_count": "",
        "filing_date": "",
    }
    used_filings = []
    if revenue:
        latest = revenue[0]
        result["revenue_fy"] = round(latest["val"] / 1_000_000, 2)  # USD millions
        used_filings.append(latest["filed"])
        prior = next((e for e in revenue[1:] if 330 <=
                      (dt.date.fromisoformat(latest["end"]) - dt.date.fromisoformat(e["end"])).days <= 400), None)
        if prior and prior["val"] > 0:
            result["revenue_growth_pct"] = round((latest["val"] / prior["val"] - 1) * 100, 2)
        match = next((e for e in earnings if e["start"] == latest["start"] and e["end"] == latest["end"]), None)
        if match and latest["val"] > 0:
            result["net_margin_pct"] = round(match["val"] / latest["val"] * 100, 2)
            used_filings.append(match["filed"])
    if eps:
        result["eps_diluted"] = round(float(eps[0]["val"]), 4)
        result["eps_target_price"] = round(float(eps[0]["val"]) * business_multiple, 2)
        used_filings.append(eps[0]["filed"])
    if cashflow:
        result["operating_cashflow_fy"] = round(float(cashflow[0]["val"]) / 1_000_000, 2)
        matching_shares = next((entry for entry in diluted_shares
                                if entry["start"] == cashflow[0]["start"] and entry["end"] == cashflow[0]["end"]), None)
        if matching_shares and matching_shares["val"] > 0:
            cashflow_per_share = float(cashflow[0]["val"]) / float(matching_shares["val"])
            result["operating_cashflow_per_share"] = round(cashflow_per_share, 4)
            result["cashflow_target_price"] = round(cashflow_per_share * business_multiple, 2)
            used_filings.extend((cashflow[0]["filed"], matching_shares["filed"]))
    if equity:
        matching_shares = next((entry for entry in shares_outstanding if entry["end"] == equity[0]["end"]), None)
        if matching_shares and matching_shares["val"] > 0:
            book_per_share = float(equity[0]["val"]) / float(matching_shares["val"])
            result["book_value_per_share"] = round(book_per_share, 4)
            result["book_value_target_price"] = round(book_per_share * book_value_multiple, 2)
            used_filings.extend((equity[0]["filed"], matching_shares["filed"]))
    targets = (
        ("eps_target_price", "eps_signal"),
        ("cashflow_target_price", "cashflow_signal"),
        ("book_value_target_price", "book_value_signal"),
    )
    available = 0
    passed = 0
    for target_key, signal_key in targets:
        target = result[target_key]
        if target != "":
            available += 1
            if current_price is not None and float(target) > float(current_price):
                result[signal_key] = "BUY"
                passed += 1
    result["buy_signal_count"] = passed if available else ""
    result["filing_date"] = max(used_filings, default="")
    return result


def compute_stats(symbol, name, bars, source="Alpaca historical data"):
    valid = sorted(
        (b for b in bars if b.get("c") is not None and b.get("h") is not None and b.get("v") is not None),
        key=lambda b: b["t"],
    )
    if not valid or float(valid[-1]["c"]) <= 0:
        return None
    latest = valid[-1]
    close = float(latest["c"])
    previous = float(valid[-21]["c"]) if len(valid) >= 21 else 0
    year_start = dt.date.fromisoformat(latest["t"][:10]) - dt.timedelta(days=365)
    annual = [b for b in valid if dt.date.fromisoformat(b["t"][:10]) >= year_start]
    return {
        "symbol": symbol, "name": name, "asof": latest["t"][:10], "close": round(close, 4),
        "avg_volume_20": round(sum(float(b["v"]) for b in valid[-20:]) / 20) if len(valid) >= 20 else "",
        "return_20_pct": round((close / previous - 1) * 100, 2) if previous > 0 else "",
        "high_52w": round(max(float(b["h"]) for b in annual), 4), "source": source,
    }


CRITERIA_KEYS = (
    "minPrice", "maxPrice", "minVolume", "minReturn", "minRevenue", "minGrowth", "minMargin",
    "minEpsTarget", "minCashflowTarget", "minBookTarget", "minBuySignals",
)
SEC_CRITERIA = (
    "minRevenue", "minGrowth", "minMargin", "minEpsTarget", "minCashflowTarget",
    "minBookTarget", "minBuySignals",
)


def normalize_criteria(raw):
    criteria = {}
    for key in CRITERIA_KEYS:
        value = raw.get(key) if isinstance(raw, dict) else None
        if value is None or value == "":
            criteria[key] = None
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number or null.")
        else:
            criteria[key] = float(value)
    include_valuation = raw.get("includeValuation", False) if isinstance(raw, dict) else False
    if not isinstance(include_valuation, bool):
        raise ValueError("includeValuation must be true or false.")
    criteria["includeValuation"] = include_valuation
    for key in ("businessMultiple", "bookValueMultiple"):
        value = raw.get(key) if isinstance(raw, dict) else None
        if value is None or value == "":
            criteria[key] = None
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number or null.")
        elif value <= 0:
            raise ValueError(f"{key} must be greater than zero.")
        else:
            criteria[key] = float(value)
    if criteria["minPrice"] is not None and criteria["minPrice"] < 0:
        raise ValueError("minPrice cannot be negative.")
    if criteria["maxPrice"] is not None and criteria["maxPrice"] < 0:
        raise ValueError("maxPrice cannot be negative.")
    if criteria["minVolume"] is not None and criteria["minVolume"] < 0:
        raise ValueError("minVolume cannot be negative.")
    if criteria["minPrice"] is not None and criteria["maxPrice"] is not None and criteria["minPrice"] > criteria["maxPrice"]:
        raise ValueError("minPrice cannot exceed maxPrice.")
    if criteria["minBuySignals"] is not None and criteria["minBuySignals"] not in (0, 1, 2, 3):
        raise ValueError("minBuySignals must be a whole number between 0 and 3.")
    return criteria


def passes_minimum(value, minimum):
    return minimum is None or (value != "" and value is not None and float(value) >= minimum)


def passes_market(row, criteria):
    return (
        passes_minimum(row["close"], criteria["minPrice"])
        and (criteria["maxPrice"] is None or float(row["close"]) <= criteria["maxPrice"])
        and passes_minimum(row["avg_volume_20"], criteria["minVolume"])
        and passes_minimum(row["return_20_pct"], criteria["minReturn"])
    )


def passes_sec(row, criteria):
    return (
        passes_minimum(row["revenue_fy"], criteria["minRevenue"])
        and passes_minimum(row["revenue_growth_pct"], criteria["minGrowth"])
        and passes_minimum(row["net_margin_pct"], criteria["minMargin"])
        and passes_minimum(row["eps_target_price"], criteria["minEpsTarget"])
        and passes_minimum(row["cashflow_target_price"], criteria["minCashflowTarget"])
        and passes_minimum(row["book_value_target_price"], criteria["minBookTarget"])
        and passes_minimum(row["buy_signal_count"], criteria["minBuySignals"])
    )


def positive_env_float(name, default):
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number.") from exc
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")
    return value


def valuation_config():
    return {
        "business_multiple": positive_env_float("BUSINESS_MULTIPLE", 15),
        "book_value_multiple": positive_env_float("BOOK_VALUE_MULTIPLE", 1.5),
    }


def merge_bars(existing, additions):
    merged = {bar.get("t"): bar for bar in existing if isinstance(bar, dict) and bar.get("t")}
    merged.update({bar.get("t"): bar for bar in additions if isinstance(bar, dict) and bar.get("t")})
    return [merged[key] for key in sorted(merged)][-450:]


def market_rows(selected, alpaca, end):
    ALPACA_CACHE.mkdir(parents=True, exist_ok=True)
    path = ALPACA_CACHE / f"daily-{alpaca.feed}.json"
    cached = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                cached = payload
        except (OSError, json.JSONDecodeError):
            pass
    rows = []
    for i in range(0, len(selected), 50):
        batch = selected[i:i + 50]
        symbols = [symbol for symbol, _ in batch]
        snapshots = alpaca.snapshots(symbols)
        update_symbols = []
        for symbol in symbols:
            existing = cached.get(symbol, [])
            previous = snapshots.get(symbol, {}).get("prevDailyBar")
            previous_time = previous.get("t", "") if isinstance(previous, dict) else ""
            latest_cached = existing[-1].get("t", "") if existing else ""
            if not existing or not previous_time or previous_time > latest_cached:
                update_symbols.append(symbol)
        if update_symbols:
            starts = []
            for symbol in update_symbols:
                existing = cached.get(symbol, [])
                if existing:
                    starts.append(dt.datetime.fromisoformat(existing[-1]["t"].replace("Z", "+00:00")) - dt.timedelta(days=3))
            start = min(starts) if starts else end - dt.timedelta(days=400)
            updates = alpaca.historical_daily_bars(update_symbols, start, end)
            for symbol in update_symbols:
                cached[symbol] = merge_bars(cached.get(symbol, []), updates.get(symbol, []))
        for symbol in symbols:
            newest = []
            snapshot = snapshots.get(symbol, {})
            for field in ("prevDailyBar", "dailyBar"):
                bar = snapshot.get(field)
                if isinstance(bar, dict):
                    newest.append(bar)
            cached[symbol] = merge_bars(cached.get(symbol, []), newest)
        for symbol, name in batch:
            row = compute_stats(symbol, name, cached.get(symbol, []), f"{alpaca.source_label} + snapshot")
            if row:
                rows.append(row)
        print(f"Processed Alpaca {min(i + 50, len(selected))}/{len(selected)}; usable {len(rows)}")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(cached), encoding="utf-8")
    temporary.replace(path)
    return rows


def refresh(args, *, criteria=None, force_sec=False):
    criteria = normalize_criteria(criteria or {})
    needs_sec = criteria["includeValuation"] or any(criteria[key] is not None for key in SEC_CRITERIA)
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY before refreshing.")
    sec_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if needs_sec and (not sec_agent or "@" not in sec_agent):
        raise RuntimeError("Set SEC_USER_AGENT to your name and contact email for SEC screening.")
    feed = os.environ.get("ALPACA_DATA_FEED", "iex").strip().lower()
    defaults = valuation_config()
    business_multiple = criteria["businessMultiple"] or defaults["business_multiple"]
    book_value_multiple = criteria["bookValueMultiple"] or defaults["book_value_multiple"]
    try:
        alpaca = AlpacaClient(key, secret, feed=feed)
        sec = SecClient(sec_agent, SEC_CACHE) if needs_sec else None
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else None
    selected = universe(args.limit, symbols, alpaca)
    if not selected:
        raise RuntimeError("No eligible symbols found in Alpaca's asset list.")
    print(f"Refreshing Alpaca market data for {len(selected)} assets...")
    try:
        delay_minutes = int(os.environ.get("ALPACA_DATA_DELAY_MINUTES", "0"))
    except ValueError as exc:
        raise RuntimeError("ALPACA_DATA_DELAY_MINUTES must be a whole number.") from exc
    if not 0 <= delay_minutes <= 60:
        raise RuntimeError("ALPACA_DATA_DELAY_MINUTES must be between 0 and 60.")
    end = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=delay_minutes)
    market = [row for row in market_rows(selected, alpaca, end) if passes_market(row, criteria)]
    output = []
    sec_downloads = 0
    if needs_sec:
        mapping = sec.ticker_map()
        print(f"Alpaca filters retained {len(market)} assets; checking SEC data for survivors...")
    for row in market:
        row["cik"] = ""
        row.update({key: "" for key in HEADERS if key not in row and key not in ("symbol", "name", "asof", "source")})
        if needs_sec:
            cik = mapping.get(re.sub(r"[.\-]", "", row["symbol"]), "")
            row["cik"] = cik
            if cik:
                try:
                    if force_sec:
                        facts, downloaded = sec.company_facts(cik, force_refresh=True), True
                    else:
                        facts, downloaded = sec.current_company_facts(cik)
                    sec_downloads += int(downloaded)
                    row.update(sec_metrics(
                        facts,
                        current_price=row["close"],
                        business_multiple=business_multiple,
                        book_value_multiple=book_value_multiple,
                    ))
                    row["source"] += "; SEC Company Facts"
                except ApiError as exc:
                    if "HTTP 404" not in str(exc):
                        raise
            if not passes_sec(row, criteria):
                continue
        output.append(row)
    # Publish only after every batch succeeds, preserving the previous snapshot on failure.
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix(".csv.tmp")
    with temp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(output)
    temp.replace(OUT)
    print(f"Saved {len(output)} stocks to {OUT}")
    return output, {
        "alpaca": {"checked": True, "candidates": len(market), "feed": feed},
        "sec": {
            "checked": needs_sec,
            "candidates": len(market) if needs_sec else 0,
            "facts_downloaded": sec_downloads,
            "business_multiple": business_multiple,
            "book_value_multiple": book_value_multiple,
        },
    }


def records(demo):
    if demo:
        result = []
        for i, (s, n, c, v, r, h) in enumerate(DEMO):
            eps = round(1.8 + i * 0.7, 2)
            ocf_share = round(2.4 + i * 0.6, 2)
            book_share = round(8 + i * 3.5, 2)
            targets = (round(eps * 15, 2), round(ocf_share * 15, 2), round(book_share * 1.5, 2))
            signals = tuple("BUY" if target > c else "" for target in targets)
            row = {key: "" for key in HEADERS}
            row.update({
                "symbol": s, "name": n, "asof": "DEMO", "close": c, "avg_volume_20": v,
                "return_20_pct": r, "high_52w": h, "cik": f"000000000{i}",
                "revenue_fy": 1200 + i * 240, "revenue_growth_pct": (i - 2) * 4.2,
                "net_margin_pct": 8 + i * 2, "eps_diluted": eps,
                "operating_cashflow_fy": round(ocf_share * (100 + i * 10), 2),
                "operating_cashflow_per_share": ocf_share, "book_value_per_share": book_share,
                "business_multiple": 15, "book_value_multiple": 1.5,
                "eps_target_price": targets[0], "cashflow_target_price": targets[1],
                "book_value_target_price": targets[2], "eps_signal": signals[0],
                "cashflow_signal": signals[1], "book_value_signal": signals[2],
                "buy_signal_count": sum(bool(signal) for signal in signals),
                "filing_date": "DEMO", "source": "SYNTHETIC DEMO",
            })
            result.append(row)
        return result
    if not OUT.exists():
        return []
    with OUT.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


class Handler(BaseHTTPRequestHandler):
    demo = False
    refresh_limit = 0
    refresh_symbols = None
    refresh_lock = threading.Lock()

    def send_json(self, status, payload):
        content = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/api/stocks":
            content, kind = json.dumps({
                "demo": self.demo,
                "stocks": records(self.demo),
                "config": valuation_config(),
            }).encode(), "application/json"
        else:
            relative = "index.html" if route == "/" else route.lstrip("/")
            candidate = (FRONTEND / relative).resolve()
            frontend_root = FRONTEND.resolve()
            if frontend_root not in candidate.parents or not candidate.is_file():
                self.send_error(404)
                return
            content = candidate.read_bytes()
            kind = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind in ("application/javascript", "application/json"):
                kind += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store" if route == "/api/stocks" else "public, max-age=3600")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if urlparse(self.path).path != "/api/screen":
            self.send_error(404)
            return
        if self.demo:
            self.send_json(409, {"error": "Live screening is unavailable in demo mode."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Invalid request length."})
            return
        if length > 65536:
            self.send_json(413, {"error": "Screen request is too large."})
            return
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Screen request must contain valid JSON."})
            return
        if not isinstance(request, dict) or not isinstance(request.get("criteria", {}), dict):
            self.send_json(400, {"error": "Screen criteria must be an object."})
            return
        if not self.refresh_lock.acquire(blocking=False):
            self.send_json(409, {"error": "A provider refresh is already in progress."})
            return
        try:
            args = SimpleNamespace(limit=self.refresh_limit, symbols=self.refresh_symbols)
            output, providers = refresh(args, criteria=request.get("criteria", {}))
            self.send_json(200, {
                "demo": False,
                "refreshed": True,
                "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "stocks": output,
                "providers": providers,
            })
        except (ApiError, RuntimeError, ValueError) as exc:
            self.send_json(502, {"error": str(exc)})
        finally:
            self.refresh_lock.release()


def main():
    load_env_file(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Fetch latest eligible daily data")
    parser.add_argument("--demo", action="store_true", help="Show synthetic sample data")
    try:
        default_limit = int(os.environ.get("MARKETNUANCE_SCREEN_LIMIT", "0"))
    except ValueError:
        parser.error("MARKETNUANCE_SCREEN_LIMIT must be a whole number")
    parser.add_argument("--limit", type=int, default=default_limit, help="Maximum symbols for refresh; 0 means all (default: 0)")
    parser.add_argument("--symbols", help="Optional comma-separated symbols to refresh")
    parser.add_argument("--host", default="127.0.0.1", help="Server bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be zero or positive")
    if args.refresh:
        refresh(args)
        return
    Handler.demo = args.demo
    Handler.refresh_limit = args.limit
    Handler.refresh_symbols = args.symbols
    with ThreadingHTTPServer((args.host, args.port), Handler) as server:
        print(f"Serving MarketNuance on {args.host}:{args.port}  (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
