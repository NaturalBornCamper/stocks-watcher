from urllib.parse import urlencode


def carry_context(request):
    """Read URL params that should carry across view switches (sort, gating
    filters) and build a query-string fragment for menu/date-selector links.
    min_score is deliberately NOT carried -- its scale differs per algorithm."""
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
