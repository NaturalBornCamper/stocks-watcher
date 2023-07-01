import requests

from watcher.models import Stock, Price
from watcher.utils import getenv

# https://www.alphavantage.co/documentation/

BASE_URL = "https://www.alphavantage.co/query"


def fetch(stock: Stock, get_full_price_history: bool) -> list[Price] | str:
    api_request = requests.get(
        BASE_URL,
        params={
            'function': 'TIME_SERIES_DAILY_ADJUSTED',  # if it stops working: "TIME_SERIES_DAILY"
            'symbol': stock.google_ticker,
            'outputsize': 'full' if get_full_price_history else 'compact',
            'apikey': getenv("ALPHAVANTAGE_API_KEY"),
        }
    )

    result = []
    if api_request.headers.get('content-type') == "application/json":
        json = api_request.json()
        if "Time Series (Daily)" in json:
            for date, details in json["Time Series (Daily)"].items():
                result.append(
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
        else:
            result = f"{api_request.request.url} ({api_request.status_code})\n {json['Error Message']}"
    else:
        result = f"{api_request.request.url} ({api_request.status_code})\n {api_request.content}"

    return result

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
