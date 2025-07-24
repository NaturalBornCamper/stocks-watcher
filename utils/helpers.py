import os
from typing import Union

from constants import CURRENCY_USD, CURRENCY_SYMBOL_USD, CURRENCY_CAD, CURRENCY_SYMBOL_CAD


def getenv(key: str, default=None) -> Union[str, int, bool]:
    # ENV variable not found in system AND no fallback value was provided
    if key not in os.environ and default is None:
        raise ValueError(f"Error: ENV variable <{key}> missing")

    val = os.environ.get(key, default)

    if isinstance(val, str):
        if val.lower() == "true":
            return True
        elif val.lower() == "false":
            return False

    return val


def get_currency_symbol(currency: str) -> str:
    if currency == CURRENCY_USD:
        return CURRENCY_SYMBOL_USD
    elif currency == CURRENCY_CAD:
        return CURRENCY_SYMBOL_CAD
    else:
        return ""