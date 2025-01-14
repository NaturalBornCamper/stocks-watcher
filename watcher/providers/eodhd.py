from datetime import datetime, timedelta

import requests
from requests import Response

from watcher.models import Stock, Price
from watcher.providers.base_provider import AbstractBaseProvider
from watcher.utils.helpers import getenv


# https://eodhistoricaldata.com/cp/settings/api-usage

class EODHD(AbstractBaseProvider):
    API_NAME = "EOD Historical Data"
    BASE_URL = "https://eodhistoricaldata.com/api/eod"
    CAD_SUFFIX = ".TO"

    @staticmethod
    def fetch(stock: Stock, get_full_price_history: bool) -> dict:
        symbol = stock.symbol
        today = datetime.today()
        from_date = (today - timedelta(days=365)) if get_full_price_history else (today - timedelta(days=7))
        if symbol:
            api_request = requests.get(
                f"{EODHD.BASE_URL}/{symbol}",
                params={
                    'api_token': getenv('EODHD_API_KEY'),
                    'fmt': 'json',
                    'period': 'daily',
                    'from': from_date.strftime('%Y-%m-%d'),
                },
            )
            api_result = {
                "url": api_request.request.url,
                "status_code": api_request.status_code,
                "prices": [],
            }
        else:
            return {
                "url": "empty",
                "status_code": 0,
                "prices": [],
                "success": False,
                "message": f"No symbol provided for {stock.name}"
            }

        try:
            json = api_request.json()
        except requests.exceptions.JSONDecodeError:
            api_result["success"] = False
            api_result["message"] = api_request.text
            return api_result

        if type(json) is list:
            for details in json:
                api_result["prices"].append(
                    Price(
                        stock=stock,
                        date=details["date"],
                        low=details["low"],
                        high=details["high"],
                        open=details["open"],
                        close=details["adjusted_close"],
                        volume=details["volume"],
                    )
                )
            api_result["success"] = True
        else:
            api_result["success"] = False
            api_result["message"] = EODHD.get_json_error(api_request, json, True)

        return api_result

    @staticmethod
    def get_json_error(api_request: Response, json: dict, incorrect_json_format: bool = False) -> str:
        if incorrect_json_format:
            return f"Received json data is not a list as expected json: {api_request.text}"
        else:
            return api_request.text
