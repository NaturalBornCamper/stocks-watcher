import copy
from datetime import date as date_cls

from django.db.models import Max
from django.http import Http404, HttpResponse
from django.template import loader

from apps.quant.models import (
    SARating, CompiledSAScore, CompiledSAScoreDecayed, CompiledSAScoreMomentum,
)

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


def _carry_context(request):
    """Read URL params that should carry across view switches (sort, gating
    filters) and build a query-string fragment for menu/date-selector links.
    min_score is deliberately NOT carried -- its scale differs per algorithm."""
    from urllib.parse import urlencode

    sort = request.GET.get("sort")
    direction = request.GET.get("dir")
    hide_red = request.GET.get("hide_red") == "1"
    hide_orange = request.GET.get("hide_orange") == "1"
    hide_yellow = request.GET.get("hide_yellow") == "1"

    params = {}
    if sort is not None:
        params["sort"] = sort
        params["dir"] = direction or "asc"
    if hide_red:
        params["hide_red"] = "1"
    if hide_orange:
        params["hide_orange"] = "1"
    if hide_yellow:
        params["hide_yellow"] = "1"

    return {
        "sort_param": sort,
        "dir_param": (direction or "asc") if sort is not None else None,
        "hide_red": hide_red,
        "hide_orange": hide_orange,
        "hide_yellow": hide_yellow,
        "carry_query": ("?" + urlencode(params)) if params else "",
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
    # reads the params via _carry_context so menu links and the checkbox `checked`
    # state stay consistent on initial load.
    template = loader.get_template("score_and_count.html")
    context = {
        "quant_list": quant_list,
        "value_to_display": value_to_display,
        "min_score_input": min_score_input,
        "min_score_default": DEFAULT_MIN_SCORES.get(value_to_display, 0),
        **_carry_context(request),
    }
    return HttpResponse(template.render(context, request))


# TODO See specific SA rating category for a specific month (just like on Seeking Alpha) [/sa/historical/<type>/<date>]
# TODO Get distinct dates from DB and create menu on top to avoid having to write manually in URL bar
def historical(request, type: str, date: str = None):
    pass


def stock(request, symbol: str):
    pass


# Per-month grid: for a chosen month, shows each stock's RANK in each SA category
# (plus the historical count of times it has been ranked in that category).
# date_str is "YYYY-MM"; if omitted, falls back to the latest available month.
def month_view(request, date_str=None):
    if date_str:
        try:
            year, month = date_str.split("-")
            chosen_date = date_cls(int(year), int(month), 1)
        except (ValueError, AttributeError):
            raise Http404(f"Bad month format (expected YYYY-MM): {date_str}")
    else:
        chosen_date = SARating.objects.aggregate(Max("date"))["date__max"]
        if not chosen_date:
            raise Http404("No SA ratings imported yet")

    # All distinct months for the top navigation, newest first.
    available_dates = list(
        SARating.objects.values_list("date", flat=True).distinct().order_by("-date")
    )

    # Ratings for the chosen month, with stock pulled in via JOIN (no N+1).
    ratings = list(
        SARating.objects.filter(date=chosen_date).select_related("sa_stock")
    )

    # Counts per (sa_stock_id, type) for stocks present in the chosen month,
    # so each cell can show "rank (count-historical)".
    stock_ids = {r.sa_stock_id for r in ratings}
    counts = {
        (c.sa_stock_id, c.type): c.count
        for c in CompiledSAScore.objects.filter(sa_stock_id__in=stock_ids)
    }

    # Default cell shape per type (rank blank if the stock isn't in that type this month).
    default_types = {slug: {"rank": "", "count": 0} for slug in SARating.TYPES}

    quant_list = {}
    for r in ratings:
        sym = r.sa_stock.symbol
        if sym not in quant_list:
            quant_list[sym] = {
                "name": r.sa_stock.name,
                "types": copy.deepcopy(default_types),
                "row_class": "",  # gating not meaningful in a per-month view
            }
        quant_list[sym]["types"][r.type] = {
            "rank": r.rank,
            "count": counts.get((r.sa_stock_id, r.type), 0),
        }

    template = loader.get_template("month_view.html")
    context = {
        "quant_list": quant_list,
        "value_to_display": "rank",
        "available_dates": available_dates,
        "chosen_date": chosen_date,
        **_carry_context(request),
    }
    return HttpResponse(template.render(context, request))
