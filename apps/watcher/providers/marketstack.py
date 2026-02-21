from datetime import datetime, timedelta

import requests
from requests import Response

from apps.watcher.models import Stock, Price
from apps.watcher.providers.base_provider import AbstractBaseProvider
from utils.helpers import getenv


# Usage https://marketstack.com/usage
# https://marketstack.com/documentation_v2
# https://docs.apilayer.com/marketstack/docs/marketstack-api-v2-v-2-0-0#/End-of-day/get_eod
# To find stock symbols (mostly Canadian stocks): https://marketstack.com/search

class MarketStack(AbstractBaseProvider):
    API_NAME = "Marketstack"
    BASE_URL = "http://api.marketstack.com/v2/eod"
    CAD_SUFFIX = ".TO"

    @classmethod
    def fetch(cls, stock: Stock, get_full_price_history: bool) -> dict:
        params = {
            "access_key": getenv("MARKETSTACK_API_KEY"),
            "symbols": cls.get_symbol(stock),
            "sort": "DESC",
            "limit": "1000" if get_full_price_history else "7",
        }
        if not get_full_price_history:
            params["date_from"] = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")

        api_request = requests.get(cls.BASE_URL, params=params)
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

        if "error" in json:
            api_result["success"] = False
            api_result["message"] = cls.get_json_error(api_request, json)
            return api_result

        if "data" not in json:
            api_result["success"] = False
            api_result["message"] = cls.get_json_error(api_request, json, "data")
            return api_result

        if type(json["data"]) is not list:
            api_result["success"] = False
            api_result["message"] = cls.get_json_error(api_request, json, "list[data]")
            return api_result

        for details in json["data"]:
            api_result["prices"].append(
                Price(
                    stock=stock,
                    date=details["date"].split("T")[0],
                    low=details.get("adj_low") or details["low"],
                    high=details.get("adj_high") or details["high"],
                    open=details.get("adj_open") or details["open"],
                    close=details.get("adj_close") or details["close"],
                    volume=details.get("adj_volume") or details["volume"],
                )
            )

        api_result["success"] = True

        return api_result

    @classmethod
    def get_json_error(cls, api_request: Response, json: dict, missing_parameter: str = "") -> str:
        if error_message := json.get("error", {}).get("message"):
            return error_message
        elif missing_parameter:
            return f"\"{missing_parameter}\" not found in json: {api_request.text}"
        else:
            return api_request.text
