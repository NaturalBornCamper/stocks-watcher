from abc import ABC, abstractmethod

from requests import Response

from watcher.models import Stock


class AbstractBaseProvider(ABC):
    API_NAME = ""
    BASE_URL = ""
    CAD_SUFFIX = ""

    @staticmethod
    @abstractmethod
    def fetch(stock: Stock, get_full_price_history: bool):
        pass

    @staticmethod
    @abstractmethod
    def get_json_error(api_request: Response, json: dict, missing_parameter: str = "") -> str:
        return ""
