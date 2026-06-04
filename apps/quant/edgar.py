import json
import time

import requests
from django.conf import settings

# SEC's free ticker -> CIK mapping. The CIK identifies the company (the legal
# entity that files with the SEC), so it stays the same even when a company
# changes its ticker symbol or its name. That makes it a good stable id.
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CACHE_FILE = settings.BASE_DIR / "data_dumps" / "_edgar_company_tickers.json"
# SEC asks every caller to identify itself in the User-Agent header.
USER_AGENT = "Personal Stocks Watcher (edgar@ashgun.com)"
# Re-download the mapping only when our cached copy is older than this.
CACHE_MAX_AGE_DAYS = 7


def normalize_ticker(symbol: str) -> str:
    """Make tickers comparable across sources. SEC writes share classes with a
    hyphen (BRK-A) while Seeking Alpha uses a dot (BRK.A), so turn hyphens into
    dots. We do NOT strip the separator entirely: that would wrongly merge a
    preferred ticker like T-PC into the common ticker TPC."""
    return symbol.upper().replace("-", ".")


def load_ticker_to_cik() -> dict:
    """Return a dict of {normalized ticker: CIK string} from SEC EDGAR.

    The file is downloaded once and cached on disk. If the download fails and we
    have no cache, an empty dict is returned so the caller can carry on without CIKs."""
    data = _load_cached_or_download()

    ticker_to_cik = {}
    for entry in data.values():
        ticker = entry.get("ticker", "")
        cik = entry.get("cik_str")
        if ticker and cik is not None:
            ticker_to_cik[normalize_ticker(ticker)] = str(cik)
    return ticker_to_cik


def _load_cached_or_download() -> dict:
    # Use the cached file if it is still fresh
    if CACHE_FILE.exists():
        age_days = (time.time() - CACHE_FILE.stat().st_mtime) / 86400
        if age_days < CACHE_MAX_AGE_DAYS:
            with open(CACHE_FILE, "r", encoding="utf-8") as file:
                return json.load(file)

    # Otherwise download a fresh copy and cache it
    try:
        response = requests.get(EDGAR_TICKERS_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        data = response.json()
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file)
        return data
    except (requests.RequestException, ValueError):
        # Download failed: fall back to a stale cache if we have one, else give up
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        return {}