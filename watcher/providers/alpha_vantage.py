import requests
from requests import Response

from watcher.models import Stock, Price
from watcher.utils import getenv

# https://www.alphavantage.co/documentation/

API_NAME = "Alpha Vantage"
BASE_URL = "https://www.alphavantage.co/query"


def fetch(stock: Stock, get_full_price_history: bool) -> dict:
    symbol = stock.alphavantage_symbol if stock.alphavantage_symbol else stock.symbol
    if symbol:
        api_request = requests.get(
            BASE_URL,
            params={
                'function': 'TIME_SERIES_DAILY_ADJUSTED',  # if it stops working: "TIME_SERIES_DAILY"
                'symbol': stock.symbol,
                'outputsize': 'full' if get_full_price_history else 'compact',
                'apikey': getenv("ALPHAVANTAGE_API_KEY"),
            }
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

    if "Time Series (Daily)" in json:
        for date, details in json["Time Series (Daily)"].items():
            api_result["prices"].append(
                Price(
                    stock=stock,
                    date=date,
                    low=details.get("3. low"),
                    high=details.get("2. high"),
                    open=details.get("1. open"),
                    close=details.get("5. adjusted close", details.get("4. close")),
                    volume=details.get("6. volume"),
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

# AMZN stock split example AlphaVantage
# https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=amzn&outputsize=full&apikey=XX
# "2022-06-07": {
#     "1. open": "122.005",
#     "2. high": "124.1",
#     "3. low": "120.63",
#     "4. close": "123.0",
#     "5. adjusted close": "123.0",
#     "6. volume": "85156712",
#     "7. dividend amount": "0.0000",
#     "8. split coefficient": "1.0"
# },
# "2022-06-06": {
#     "1. open": "125.245",
#     "2. high": "128.99",
#     "3. low": "123.81",
#     "4. close": "124.79",
#     "5. adjusted close": "124.79",
#     "6. volume": "134271125",
#     "7. dividend amount": "0.0000",
#     "8. split coefficient": "20.0"
# },
# "2022-06-03": {
#     "1. open": "2484.0",
#     "2. high": "2488.0",
#     "3. low": "2420.929",
#     "4. close": "2447.0",
#     "5. adjusted close": "122.35",
#     "6. volume": "4880166",
#     "7. dividend amount": "0.0000",
#     "8. split coefficient": "1.0"
# },