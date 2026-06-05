# Drill-down views showing raw SA ranks for a single slice: one month across
# all stocks, or one stock across all months. The compiled-score grids live in
# score.py.
import copy
from datetime import date as date_cls

from django.db.models import Max
from django.http import Http404, HttpResponse
from django.template import loader

from apps.quant.models import SAStock, SARating, CompiledSAScore
from apps.quant.views.shared import carry_context


# TODO See specific SA rating category for a specific month (just like on Seeking Alpha) [/sa/historical/<type>/<date>]
# TODO Get distinct dates from DB and create menu on top to avoid having to write manually in URL bar
def historical(request, type: str, date: str = None):
    pass


# Single-stock history: one row per month (newest first), one column per SA
# category, each cell showing the rank the stock held that month (blank = not
# in that category's top-100).
def stock(request, symbol: str):
    try:
        sa_stock = SAStock.objects.get(symbol__iexact=symbol)
    except SAStock.DoesNotExist:
        raise Http404(f"Unknown stock symbol: {symbol}")

    # Default cell shape per category (rank blank if the stock wasn't ranked).
    default_types = {slug: {"rank": "", "quant": None} for slug in SARating.TYPES}

    # Group the stock's ratings into one row per month. Dict insertion order
    # follows the query order, so rows come out newest first.
    months = {}
    for rating in SARating.objects.filter(sa_stock=sa_stock).order_by("-date"):
        if rating.date not in months:
            months[rating.date] = copy.deepcopy(default_types)
        months[rating.date][rating.type] = {"rank": rating.rank, "quant": rating.quant}

    template = loader.get_template("stock_details.html")
    context = {
        "sa_stock": sa_stock,
        "months": months,
        **carry_context(request),
    }
    return HttpResponse(template.render(context, request))


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
        **carry_context(request),
    }
    return HttpResponse(template.render(context, request))
