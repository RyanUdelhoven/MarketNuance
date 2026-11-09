"""SEC ticker-association and Company Facts client."""

import json
from pathlib import Path
import re
import time

from noodle_analytics.http_client import ApiError, JsonHttpClient


class SecClient:
    TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

    def __init__(self, user_agent, cache_dir, *, cache_ttl=7 * 86400, pause=0.22, http=None, clock=time.time, sleep=time.sleep):
        if not user_agent or "@" not in user_agent:
            raise ValueError("SEC_USER_AGENT must contain your name and contact email.")
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir)
        self.cache_ttl = cache_ttl
        self.pause = pause
        self.clock = clock
        self.sleep = sleep
        self.http = http or JsonHttpClient(user_agent=user_agent)

    def ticker_map(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / "ticker-map.json"
        if path.exists() and self.clock() - path.stat().st_mtime < 86400:
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(cached, dict):
                    return cached
            except (OSError, json.JSONDecodeError):
                pass
        payload = self.http.get(self.TICKERS_URL, headers={"User-Agent": self.user_agent})
        if not isinstance(payload, dict):
            raise ApiError("SEC ticker response must be an object.")
        mapping = {}
        for entry in payload.values():
            if not isinstance(entry, dict) or "ticker" not in entry or "cik_str" not in entry:
                continue
            ticker = re.sub(r"[.\-]", "", str(entry["ticker"]).upper())
            mapping[ticker] = str(entry["cik_str"]).zfill(10)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(mapping), encoding="utf-8")
        temporary.replace(path)
        return mapping

    def submissions(self, cik):
        if not re.fullmatch(r"\d{10}", str(cik)):
            raise ValueError("SEC CIK must contain exactly 10 digits.")
        self.sleep(self.pause)
        payload = self.http.get(
            self.SUBMISSIONS_URL.format(cik=cik),
            headers={"User-Agent": self.user_agent},
        )
        if not isinstance(payload, dict):
            raise ApiError("SEC submissions response must be an object.")
        return payload

    def current_company_facts(self, cik):
        """Check current filing metadata and download facts only when annual data changed."""
        path = self.cache_dir / f"{cik}.json"
        cached = None
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        submissions = self.submissions(cik)
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", []) if isinstance(recent, dict) else []
        dates = recent.get("filingDate", []) if isinstance(recent, dict) else []
        newest_annual = max(
            (date for form, date in zip(forms, dates) if form in ("10-K", "10-K/A")),
            default="",
        )
        cached_filed = self._latest_filed(cached) if cached else ""
        if cached is not None and (not newest_annual or newest_annual <= cached_filed):
            return cached, False
        return self.company_facts(cik, force_refresh=True), True

    @staticmethod
    def _latest_filed(payload):
        latest = ""
        for taxonomy in payload.get("facts", {}).values():
            if not isinstance(taxonomy, dict):
                continue
            for concept in taxonomy.values():
                for entries in concept.get("units", {}).values() if isinstance(concept, dict) else []:
                    for entry in entries if isinstance(entries, list) else []:
                        if entry.get("form") in ("10-K", "10-K/A"):
                            latest = max(latest, str(entry.get("filed", "")))
        return latest

    def company_facts(self, cik, *, force_refresh=False):
        if not re.fullmatch(r"\d{10}", str(cik)):
            raise ValueError("SEC CIK must contain exactly 10 digits.")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{cik}.json"
        if not force_refresh and path.exists() and self.clock() - path.stat().st_mtime < self.cache_ttl:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        self.sleep(self.pause)
        payload = self.http.get(
            self.FACTS_URL.format(cik=cik),
            headers={"User-Agent": self.user_agent},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("facts", {}), dict):
            raise ApiError("SEC Company Facts response has an invalid shape.")
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(path)
        return payload
