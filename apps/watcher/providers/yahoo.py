from datetime import datetime, timedelta, timezone

import requests
from requests import Response

from apps.watcher.models import Stock, Price
from apps.watcher.providers.base_provider import AbstractBaseProvider


# Yahoo Finance public chart API. No API key needed, no documented rate limit,
# and it returns adjusted close. This is the same source used by the backtest
# research command (apps/quant/management/commands/backtest_scores.py).
# https://query1.finance.yahoo.com/v8/finance/chart/AAPL

class Yahoo(AbstractBaseProvider):
    API_NAME = "Yahoo Finance"
    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
    CAD_SUFFIX = ".TO"
    # Yahoo blocks requests without a browser-like User-Agent.
    HEADERS = {"User-Agent": "Mozilla/5.0 (Stocks Watcher price fetcher)"}

    @classmethod
    def fetch(cls, stock: Stock, get_full_price_history: bool) -> dict:
        today = datetime.now(timezone.utc)
        from_date = (today - timedelta(days=730)) if get_full_price_history else (today - timedelta(days=7))
        api_request = requests.get(
            f"{cls.BASE_URL}/{cls.get_symbol(stock)}",
            params={
                "period1": int(from_date.timestamp()),
                "period2": int(today.timestamp()),
                "interval": "1d",
                "includeAdjustedClose": "true",
            },
            headers=cls.HEADERS,
        )
        api_result = {
            "url": api_request.request.url,
            "status_code": api_request.status_code,
            "prices": [],
        }

        try:
            json = api_request.json()
        except requests.exceptions.JSONDecodeError:
            api_result["success"] = False
            api_result["message"] = api_request.text
            return api_result

        result = (json.get("chart", {}).get("result") or [None])[0]
        if not result or "timestamp" not in result:
            api_result["success"] = False
            api_result["message"] = cls.get_json_error(api_request, json)
            return api_result

        # Daily values: open/high/low/close/volume come from "quote"; the
        # split/dividend-adjusted close comes from "adjclose" when present.
        quote = result["indicators"]["quote"][0]
        adjclose = (result["indicators"].get("adjclose") or [{}])[0].get("adjclose")
        for index, timestamp in enumerate(result["timestamp"]):
            close = adjclose[index] if adjclose else quote["close"][index]
            # Yahoo leaves gaps as null (e.g. non-trading days); skip those rows.
            if None in (quote["open"][index], quote["high"][index], quote["low"][index],
                        close, quote["volume"][index]):
                continue
            api_result["prices"].append(
                Price(
                    stock=stock,
                    date=datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d"),
                    low=quote["low"][index],
                    high=quote["high"][index],
                    open=quote["open"][index],
                    close=close,
                    volume=quote["volume"][index],
                )
            )

        api_result["success"] = True
        return api_result

    @classmethod
    def get_json_error(cls, api_request: Response, json: dict, missing_parameter: str = "") -> str:
        error = json.get("chart", {}).get("error")
        if error:
            return error.get("description") or str(error)
        return f"No price data in json: {api_request.text}"