# Grids of the compiled per-stock scores (all-time / decayed / momentum) and
# the presence-count view. The raw-rank drill-downs (per-month, per-stock)
# live in ranks.py.
import copy

from django.http import HttpResponse
from django.template import loader

from apps.quant.models import (
    SARating, CompiledSAScore, CompiledSAScoreDecayed, CompiledSAScoreMomentum,
)
from apps.quant.views.shared import carry_context

SA_MODEL_BY_DISPLAY = {
    "score_decay": CompiledSAScoreDecayed,
    "score_momentum": CompiledSAScoreMomentum,
}

# Per-view default minimum score (or count, for the count view) used to hide
# stocks below the threshold. Different per algorithm because scales differ:
# all-time scores can reach thousands while a 3-month decayed score caps around 175.
DEFAULT_MIN_SCORES = {
    "score": 600,           # all-time cumulative; large numbers
    "score_decay": 60,      # 3-month exponential decay; max ~175
    "score_momentum": 30,   # base + 2*momentum; can be negative
    "count": 10,             # # of months in any category's top-100
}


def _parse_min_score(request, value_to_display):
    """Read ?min_score=... from the URL.
    - missing param  -> use per-view default
    - empty param    -> None (show everything)
    - invalid param  -> fall back to default
    Returns (applied_threshold_or_None, value_for_input_field)."""
    raw = request.GET.get("min_score")
    if raw is None:
        default = DEFAULT_MIN_SCORES.get(value_to_display, 0)
        return default, str(default)
    if raw == "":
        return None, ""
    try:
        return int(raw), raw
    except ValueError:
        default = DEFAULT_MIN_SCORES.get(value_to_display, 0)
        return default, str(default)


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

    # Filter: hide stocks below the threshold. The filter applies to any cell's
    # score (or count, on the count view); a stock with even one cell at/above
    # the threshold stays visible.
    min_score, min_score_input = _parse_min_score(request, value_to_display)
    if min_score is not None and min_score > 0:
        filter_key = "count" if value_to_display == "count" else "score"
        quant_list = {
            sym: stock for sym, stock in quant_list.items()
            if any(t[filter_key] >= min_score for t in stock["types"].values())
        }

    # Note: the hide_red / hide_orange / hide_yellow flags are NOT applied here.
    # They are live (no Apply button), so all rows are sent and the checkbox state
    # is toggled via CSS classes by static/js/gated-filter.js. The server still
    # reads the params via carry_context so menu links and the checkbox `checked`
    # state stay consistent on initial load.
    template = loader.get_template("score_and_count.html")
    context = {
        "quant_list": quant_list,
        "value_to_display": value_to_display,
        "min_score_input": min_score_input,
        "min_score_default": DEFAULT_MIN_SCORES.get(value_to_display, 0),
        **carry_context(request),
    }
    return HttpResponse(template.render(context, request))
