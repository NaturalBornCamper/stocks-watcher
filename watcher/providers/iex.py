import requests

from watcher.models import Stock, Price
from watcher.utils import getenv

# https://iexcloud.io/docs/core/HISTORICAL_PRICES

BASE_URL = "https://api.iex.cloud/v1/data/core/historical_prices/"


def fetch(stock: Stock, get_full_price_history: bool) -> list[Price] | str:
    api_request = requests.get(
        BASE_URL + stock.google_ticker,
        params={
            'range': '1y' if get_full_price_history else '1w',
            'token': getenv("IEX_API_KEY"),
        }
    )

    result = []
    if api_request.headers.get('content-type') == "application/json":
        json = api_request.json()
        if type(json) is list:
            for details in api_request.json():
                result.append(
                    Price(
                        stock=stock,
                        date=details.get("priceDate"),
                        low=details.get("low"),
                        high=details.get("high"),
                        open=details.get("open"),
                        close=details.get("close"),
                        volume=details.get("volume"),
                    )
                )
            return result
        else:
            result = f"{api_request.request.url} ({api_request.status_code})\n {api_request.content}"
    else:
        result = f"{api_request.request.url} ({api_request.status_code})\n {api_request.content}"

    return result

# AMZN stock split example IEX
# https://api.iex.cloud/v1/data/core/historical_prices/amzn?range=14m&token=XX
# {"close":124.79,"fclose":124.79,"fhigh":128.99,"flow":123.81,"fopen":125.245,"fvolume":135269024,"high":128.99,"low":123.81,"open":125.245,"priceDate":"2022-06-06","symbol":"AMZN","uclose":124.79,"uhigh":128.99,"ulow":123.81,"uopen":125.245,"uvolume":135269024,"volume":135269024,"id":"HISTORICAL_PRICES","key":"AMZN","subkey":"","date":1654473600000,"updated":1672269376000},
# {"close":122.35,"fclose":122.35,"fhigh":124.4,"flow":121.047,"fopen":124.2,"fvolume":97603320,"high":124.4,"low":121.047,"open":124.2,"priceDate":"2022-06-03","symbol":"AMZN","uclose":2447,"uhigh":2488,"ulow":2420.929,"uopen":2484,"uvolume":4880166,"volume":97603320,"id":"HISTORICAL_PRICES","key":"AMZN","subkey":"","date":1654214400000,"updated":1672269379000},
# {"close":125.511,"fclose":125.511,"fhigh":125.61,"flow":120.045,"fopen":121.684,"fvolume":100560680,"high":125.61,"low":120.045,"open":121.684,"priceDate":"2022-06-02","symbol":"AMZN","uclose":2510.22,"uhigh":2512.2,"ulow":2400.9,"uopen":2433.68,"uvolume":5028034,"volume":100560680,"id":"HISTORICAL_PRICES","key":"AMZN","subkey":"","date":1654128000000,"updated":1672269370000},
