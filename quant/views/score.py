import copy
from pprint import pprint

from django.http import HttpResponse
from django.template import loader

from quant.models import SARating, CompiledScore, CompiledScoreDecayed

DEFAULT_PER_PAGE = 20
INDEX_SCORE = 0
INDEX_COUNT = 1
INDEX_RANK = 3
DEFAULT_STOCK_DICT = {}
for slug, name in SARating.TYPES.items():
    # print(slug)
    # print(name)
    DEFAULT_STOCK_DICT[slug] = {
        "score": 0,
        "count": 0,
    }


# TODO Make a version of `score` with "decay", so that the older a quant score, the less value it has
#  (kind of like a fade out, so that a stock that was #1 several times in a row 5 years ago but not anymore isn't so valuable
# TODO Maybe re-split csv so that one sheet per category instead? Easier when getting data from SA but means multiple import in Python db
#  Find a way to make it perfect


# Displays a grid of either:
#  - score = Score for each stock, calculated from their rank each month (the higher the rank, the higher the score)
#  - count = Number of times each stock was in the quant
def score_or_count(request, value_to_display="score"):
    quant_list = {}
    quant_model = CompiledScoreDecayed if value_to_display == "score_decay" else CompiledScore

    for compiled_quant_stock_type in quant_model.objects.all():
        if compiled_quant_stock_type.sa_stock.symbol not in quant_list:
            quant_list[compiled_quant_stock_type.sa_stock.symbol] = {
                "name": compiled_quant_stock_type.sa_stock.name,
                "types": copy.deepcopy(DEFAULT_STOCK_DICT)
            }

        quant_list[compiled_quant_stock_type.sa_stock.symbol]["types"][compiled_quant_stock_type.type] = {
            # "company": compiled_quant_stock_type.score,
            "score": compiled_quant_stock_type.score,
            "count": compiled_quant_stock_type.count,
        }

    # pprint(quant_list)

    template = loader.get_template("score_and_count.html")
    context = {
        "quant_list": quant_list,
        "value_to_display": value_to_display,
    }
    return HttpResponse(template.render(context, request))


# TODO See specific quant category for a specific month (just like on Seeking Alpha) [/quant/historical/<type>/<date>]
# TODO Get distinct dates from DB and create menu on top to avoid having to write manually in URL bar
def historical(request, type: str, date: str = None):
    pass


def stock(request, symbol: str):
    pass
