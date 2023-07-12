import requests
from requests import Response

from watcher.models import Stock, Price
from watcher.utils import getenv

# NOTE to see usage left for stocks API: https://iexcloud.io/console/usage
# https://iexcloud.io/docs/core/HISTORICAL_PRICES

API_NAME = "IEX Cloud"
BASE_URL = "https://api.iex.cloud/v1/data/core/historical_prices"


def fetch(stock: Stock, get_full_price_history: bool) -> dict:
    symbol = stock.symbol
    if symbol:
        api_request = requests.get(
            f"{BASE_URL}/{stock.symbol}",
            params={
                'range': '10y' if get_full_price_history else '1w',
                'token': getenv("IEX_API_KEY"),
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
                    date=details["priceDate"],
                    low=details["low"],
                    high=details["high"],
                    open=details["open"],
                    close=details["close"],
                    volume=details["volume"],
                )
            )
        api_result["success"] = True
    else:
        api_result["success"] = False
        api_result["message"] = get_json_error(api_request, json)

    return api_result


def get_json_error(api_request: Response, json: dict) -> str:
    if error_message := json.get("Error Message"):
        return error_message
    elif error_message := json.get("Note"):
        return error_message
    else:
        return api_request.text

# AMZN stock split example IEX
# https://api.iex.cloud/v1/data/core/historical_prices/amzn?range=14m&token=XX
# {"close":124.79,"fclose":124.79,"fhigh":128.99,"flow":123.81,"fopen":125.245,"fvolume":135269024,"high":128.99,"low":123.81,"open":125.245,"priceDate":"2022-06-06","symbol":"AMZN","uclose":124.79,"uhigh":128.99,"ulow":123.81,"uopen":125.245,"uvolume":135269024,"volume":135269024,"id":"HISTORICAL_PRICES","key":"AMZN","subkey":"","date":1654473600000,"updated":1672269376000},
# {"close":122.35,"fclose":122.35,"fhigh":124.4,"flow":121.047,"fopen":124.2,"fvolume":97603320,"high":124.4,"low":121.047,"open":124.2,"priceDate":"2022-06-03","symbol":"AMZN","uclose":2447,"uhigh":2488,"ulow":2420.929,"uopen":2484,"uvolume":4880166,"volume":97603320,"id":"HISTORICAL_PRICES","key":"AMZN","subkey":"","date":1654214400000,"updated":1672269379000},
# {"close":125.511,"fclose":125.511,"fhigh":125.61,"flow":120.045,"fopen":121.684,"fvolume":100560680,"high":125.61,"low":120.045,"open":121.684,"priceDate":"2022-06-02","symbol":"AMZN","uclose":2510.22,"uhigh":2512.2,"ulow":2400.9,"uopen":2433.68,"uvolume":5028034,"volume":100560680,"id":"HISTORICAL_PRICES","key":"AMZN","subkey":"","date":1654128000000,"updated":1672269370000},
