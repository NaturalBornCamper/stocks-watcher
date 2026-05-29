import copy

from django.http import HttpResponse
from django.template import loader

from apps.quant.models import (
    SARating, CompiledSAScore, CompiledSAScoreDecayed, CompiledSAScoreMomentum,
)

SA_MODEL_BY_DISPLAY = {
    "score_decay": CompiledSAScoreDecayed,
    "score_momentum": CompiledSAScoreMomentum,
}

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
#  - count = Number of times each stock was in the sa rating
def score_or_count(request, value_to_display="score"):
    quant_list = {}
    sa_model = SA_MODEL_BY_DISPLAY.get(value_to_display, CompiledSAScore)

    # Gating annotation: marks each stock by whether it's still showing up in this month's and last
    # month's SA ratings. Applied to every view -- most useful on the all-time score (corpse risk)
    # and the count view, but informative on decayed/momentum too (gated rows naturally sink there).
    latest_stock_ids, prev_stock_ids = set(), set()
    recent_dates = list(
        SARating.objects.values_list("date", flat=True).distinct().order_by("-date")[:2]
    )
    if recent_dates:
        latest_stock_ids = set(
            SARating.objects.filter(date=recent_dates[0]).values_list("sa_stock_id", flat=True)
        )
    if len(recent_dates) > 1:
        prev_stock_ids = set(
            SARating.objects.filter(date=recent_dates[1]).values_list("sa_stock_id", flat=True)
        )

    for compiled_sa_stock_type in sa_model.objects.select_related("sa_stock"):
        # TODO replace statement with defaultdict instead of checking if the key exists to make it easier to read
        if compiled_sa_stock_type.sa_stock.symbol not in quant_list:
            entry = {
                "name": compiled_sa_stock_type.sa_stock.name,
                "types": copy.deepcopy(DEFAULT_STOCK_DICT),
                "row_class": "",
            }
            in_latest = compiled_sa_stock_type.sa_stock_id in latest_stock_ids
            in_prev = compiled_sa_stock_type.sa_stock_id in prev_stock_ids
            if not in_latest and not in_prev:
                entry["row_class"] = "gated-red"     # gone this month AND last month
            elif not in_latest:
                entry["row_class"] = "gated-orange"  # just dropped out this month
            elif not in_prev:
                entry["row_class"] = "gated-yellow"  # was out last month, back this month
            # else: present in both -> no row class (normal)
            quant_list[compiled_sa_stock_type.sa_stock.symbol] = entry

        quant_list[compiled_sa_stock_type.sa_stock.symbol]["types"][compiled_sa_stock_type.type] = {
            # "company": compiled_quant_stock_type.score,
            "score": compiled_sa_stock_type.score,
            "count": compiled_sa_stock_type.count,
        }

    # pprint(quant_list)

    template = loader.get_template("score_and_count.html")
    context = {
        "quant_list": quant_list,
        "value_to_display": value_to_display,
    }
    return HttpResponse(template.render(context, request))


# TODO See specific SA rating category for a specific month (just like on Seeking Alpha) [/sa/historical/<type>/<date>]
# TODO Get distinct dates from DB and create menu on top to avoid having to write manually in URL bar
def historical(request, type: str, date: str = None):
    pass


def stock(request, symbol: str):
    pass
