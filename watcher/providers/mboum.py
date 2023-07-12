from datetime import datetime

import requests
from requests import Response

from watcher.models import Stock, Price
from watcher.utils import getenv

# https://rapidapi.com/sparior/api/mboum-finance

API_NAME = "Mboum Finance"
BASE_URL = "https://mboum-finance.p.rapidapi.com/hi/history"


def fetch(stock: Stock, get_full_price_history: bool) -> dict:
    symbol = stock.symbol
    if symbol:
        api_request = requests.get(
            BASE_URL,
            params={
                'symbol': stock.symbol,
                'interval': '1d',
                'diffandsplits': 'false',
            },
            headers={
                'X-RapidAPI-Host': 'mboum-finance.p.rapidapi.com',
                'X-RapidAPI-Key': getenv('MBOUM_API_KEY'),
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

    if 'items' in json:
        for timestamp, details in json['items'].items():
            api_result["prices"].append(
                Price(
                    stock=stock,
                    date=datetime.strptime(details["date"], '%m-%d-%Y').strftime('%Y-%m-%d'),
                    low=details["low"],
                    high=details["high"],
                    open=details["open"],
                    close=details["adjclose"],
                    volume=details["volume"],
                )
            )
        api_result["success"] = True
    else:
        api_result["success"] = False
        api_result["message"] = get_json_error(api_request, json)

    return api_result


def get_json_error(api_request: Response, json: dict) -> str:
    if error_message := json.get("error"):
        return error_message
    else:
        return api_request.text
