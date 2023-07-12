from datetime import datetime

import requests
from requests import Response

from watcher.models import Stock, Price
from watcher.utils import getenv

# Usage https://marketstack.com/usage
# https://marketstack.com/documentation
# To find stock symbols (mostly Canadian stocks): https://marketstack.com/search
# Only one year data

API_NAME = "Marketstack"
BASE_URL = "http://api.marketstack.com/v1/tickers"


def fetch(stock: Stock, get_full_price_history: bool) -> dict:
    symbol = stock.marketstack_symbol if stock.marketstack_symbol else stock.symbol
    if symbol:
        api_request = requests.get(
            f"{BASE_URL}/{symbol}/eod",
            params={
                'access_key': getenv('MARKETSTACK_API_KEY'),
                'limit': '1000' if get_full_price_history else '7',
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

    if 'error' not in json:
        for details in json['data']['eod']:
            api_result["prices"].append(
                Price(
                    stock=stock,
                    date=datetime.strptime(details["date"], '%Y-%m-%dT%H:%M:%S%z').strftime('%Y-%m-%d'),
                    low=details["adj_low"] if details["adj_low"] else details["low"],
                    high=details["adj_high"] if details["adj_high"] else details["high"],
                    open=details["adj_open"] if details["adj_open"] else details["open"],
                    close=details["adj_close"] if details["adj_close"] else details["close"],
                    volume=details["adj_volume"] if details["adj_volume"] else details["volume"],
                )
            )
        api_result["success"] = True
    else:
        api_result["success"] = False
        api_result["message"] = get_json_error(api_request, json)

    return api_result


def get_json_error(api_request: Response, json: dict) -> str:
    if error_message := json.get("error", {}).get("message"):
        return error_message
    else:
        return api_request.text
