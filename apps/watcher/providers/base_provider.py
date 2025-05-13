from abc import ABC

from requests import Response

from constants import CURRENCY_CAD
from apps.watcher.models import Stock


class AbstractBaseProvider(ABC):
    API_NAME = ""
    BASE_URL = ""
    CAD_SUFFIX = ""

    @classmethod
    def get_symbol(cls, stock: Stock) -> str:
        if stock.currency == CURRENCY_CAD:
            return stock.symbol + cls.CAD_SUFFIX
        return stock.symbol

    @classmethod
    def fetch(cls, stock: Stock, get_full_price_history: bool):
        pass

    @classmethod
    def get_json_error(cls, api_request: Response, json: dict, missing_parameter: str = "") -> str:
        return ""
