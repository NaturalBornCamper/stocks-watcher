"""
!!USED BY CLAUDE TO RUN SIMULATION TESTS, NOT NEEDED FOR END-USERS!!

Backtest comparing stock-picking algorithms with a rolling, monthly-rebalanced,
top-7 portfolio. Reads SARating; writes reports to quant_simulations/.

Live approaches (see quant_simulations/SIMULATIONS_GUIDE.md for context and
the list of approaches dropped as confirmed losers):
  - decayed              : Decayed score, OLD linear curve [1, .667, .333] (kept as reference)
  - decay_x2             : Decayed score, NEW production curve [1, .5, .25]
  - momentum_rankband25  : Momentum entry, exit when actual rank > 25
  - current              : Raw top-7 by this month's rank (dead-simple baseline)
  - score_alltime        : Cumulative sum(101 - rank), no decay
  - alltime_gated        : All-time score, but only stocks still in this month's list

Mechanics (all approaches):
  - First buy: first trading day of SIM_START (default 2023-11). $2500/stock x 7 = $17,500.
  - Each later month, first trading day: sell positions per the approach's rule,
    split freed cash equally among new entrants that fill open slots.
  - Final mark-to-market: first trading day of VALUATION_MONTH (default 2026-05).

Point-in-time: scores for month M only use ratings dated <= M (no look-ahead).
Prices = Yahoo adjusted close, cached to quant_simulations/_backtest_price_cache.json.

Usage:
  python manage.py backtest_scores              # uses cache; fast
  python manage.py backtest_scores --refetch    # forces a fresh fetch (slow; needed
                                                # after extending SIM_END / PRICE_END)
"""
import json
import os
import time
from collections import defaultdict, namedtuple
from datetime import date, datetime, timezone

import requests
from django.core.management.base import BaseCommand

from apps.quant.models import SARating, SAStock
from apps.quant.scoring import get_distance_in_months, rewind_months

CATEGORIES = [
    "top_rated_overall", "top_quant", "top_growth", "top_value",
    "top_technology", "top_materials", "top_communication", "top_financial",
]

PORTFOLIO_SIZE = 7
DOLLARS_PER_STOCK = 2500.0

# Estimate of Marco's real-life category allocation (tech-heavy; light on financial/communication).
# Used only by the weighted-estimate report; tweak freely.
CATEGORY_WEIGHTS = {
    "top_technology": 7.0,
    "top_quant": 3.0,
    "top_rated_overall": 3.0,
    "top_growth": 1.5,
    "top_materials": 1.5,
    "top_value": 1.5,
    "top_communication": 0.5,
    "top_financial": 0.5,
}

SIM_START = (2023, 11)        # first BUY month (first with a full 4-month momentum window; data starts 2023-08)
SIM_END = (2026, 4)           # last rebalance/selection month
VALUATION_MONTH = (2026, 5)   # final mark-to-market (no new selection)

# Ratings months missing from the dataset. We carry the PREVIOUS month's ratings forward
# into these (synthetic, in-memory only) so (a) that month's rebalance is a no-op "hold" and
# (b) momentum slopes in neighbouring months aren't polluted by a phantom drop-out.
# Prices for these months are real -- only the ratings are missing.
MISSING_MONTHS = {(2024, 11)}


def _gen_months(start, end):
    months, (y, m) = [], start
    while (y, m) <= end:
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


SIM_MONTHS = _gen_months(SIM_START, SIM_END)
PERIOD_LABEL = (f"{SIM_START[0]}-{SIM_START[1]:02d} -> {VALUATION_MONTH[0]}-{VALUATION_MONTH[1]:02d} "
                f"({len(SIM_MONTHS)} monthly rebalances)")

RESOURCES_DIR = "quant_simulations"
PRICE_CACHE_PATH = f"{RESOURCES_DIR}/_backtest_price_cache.json"

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (backtest research script)"}

Approach = namedtuple("Approach", ["key", "label", "kind", "policy", "param"])
SimpleRating = namedtuple("SimpleRating", ["sa_stock_id", "date", "rank"])


def month_key(y, m):
    return f"{y:04d}-{m:02d}"


def exit_month_key():
    return f"{month_key(*VALUATION_MONTH)} (exit)"


# ---------------------------------------------------------------------------
# Point-in-time scoring (mirrors apps/quant/views/cron.py, restricted to <= as_of)
# ---------------------------------------------------------------------------
def score_decayed(ratings, as_of, window=3, decay_factors=None):
    if decay_factors is None:
        decay_factors = [1.0 - (i / window) for i in range(window)]  # production linear curve
    scores = defaultdict(float)
    for r in ratings:
        scores[r.sa_stock_id] += int((101 - r.rank) * decay_factors[get_distance_in_months(r.date, as_of)])
    return scores


def score_momentum(ratings, as_of, window=4, momentum_weight=2.0):
    pos_decay = [(window - i) / window for i in range(window)]
    pos_sum = sum(pos_decay)
    slope_decay = [(window - 1 - i) / (window - 1) for i in range(window - 1)]
    slope_sum = sum(slope_decay)

    values = {}
    for r in ratings:
        values.setdefault(r.sa_stock_id, [0] * window)[get_distance_in_months(r.date, as_of)] = max(0, 101 - r.rank)

    scores = {}
    for sid, vals in values.items():
        base = sum(v * w for v, w in zip(vals, pos_decay)) / pos_sum
        slopes = [vals[i] - vals[i + 1] for i in range(window - 1)]
        momentum = sum(s * w for s, w in zip(slopes, slope_decay)) / slope_sum
        scores[sid] = base + momentum_weight * momentum
    return scores


def score_alltime(ratings):
    # Mirrors the production CompiledSAScore: sum of (101 - rank) over all months, no decay.
    scores = defaultdict(float)
    for r in ratings:
        scores[r.sa_stock_id] += (101 - r.rank)
    return scores


def _median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _max_drawdown(curve):
    """Largest peak-to-trough decline (%) on an equity series."""
    peak = curve[0]
    worst = 0.0
    for v in curve:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst * 100


def top_n(scores, n=PORTFOLIO_SIZE):
    return sorted(scores, key=lambda k: (-scores[k], k))[:n]


class Command(BaseCommand):
    help = "Backtest decayed vs momentum (and momentum variants) stock-picking strategies"

    def add_arguments(self, parser):
        parser.add_argument("--refetch", action="store_true",
                            help="Ignore the price cache and refetch every symbol (slow; needed after extending the timeline)")
        parser.add_argument("--decay-window", type=int, default=3)
        parser.add_argument("--momentum-window", type=int, default=4)
        parser.add_argument("--momentum-weight", type=float, default=2.0)

    def handle(self, *args, **opts):
        self.decay_window = opts["decay_window"]
        self.momentum_window = opts["momentum_window"]
        self.momentum_weight = opts["momentum_weight"]

        self.id_to_symbol = {s.pk: s.symbol for s in SAStock.objects.all()}

        # Live approaches only. Approaches dropped after backtesting proved them dead-end (see
        # SIMULATIONS_GUIDE.md / memory): naive momentum, momentum-minhold, hysteresis, reweight,
        # blend, hybrid (#1 satellite), decay_x3/x4 (too steep), decayed2 (too short window).
        self.approaches = {
            # Decayed score family (production = decay_x2; old kept only as reference)
            "decayed": Approach("decayed", "Decayed-old linear [1,.667,.333]", "decayed", "strict", None),
            "decay_x2": Approach("decay_x2", "Decayed-new [1.0, 0.5, 0.25] (production)",
                                 "decay_curve", "strict", [1.0, 0.5, 0.25]),
            # Momentum (best-of-momentum variant only)
            "momentum_rankband25": Approach("momentum_rankband25", "Momentum + rank-band exit (<=25)",
                                            "momentum", "rank_band", 25),
            # Simple baseline (essential "is anything beating dead-simple?")
            "current": Approach("current", "Current top-7 (raw rank, monthly refresh)", "current", "strict", None),
            # All-time score family
            "score_alltime": Approach("score_alltime", "All-time score (cumulative, no decay)",
                                      "alltime", "strict", None),
            "alltime_gated": Approach("alltime_gated", "All-time score, gated to currently-ranked",
                                      "alltime_gated", "strict", None),
        }

        self.stdout.write("Phase A: computing point-in-time selections + symbol universe...")
        universe = self._symbol_universe()
        self.stdout.write(f"  {len(universe)} distinct symbols need prices.")

        self.stdout.write("Phase B: fetching/caching Yahoo prices...")
        price_map, missing = self._get_prices(universe, refetch=opts["refetch"])
        self.stdout.write(f"  priced {len(universe) - len(missing)}/{len(universe)}; missing {len(missing)}")

        self.stdout.write("Phase C: simulating all approaches...")
        results = {}  # approach_key -> {cat -> result}
        for key, approach in self.approaches.items():
            results[key] = {cat: self._simulate(approach, cat, price_map) for cat in CATEGORIES}

        self.stdout.write("Phase D: writing reports...")
        self._write_master(results, missing)
        self._write_regime_report(results)
        self._write_weighted_report(results)
        self._write_subset_report(results)
        self._write_by_category_report(results)
        self._write_detail_report(results)
        self.stdout.write(self.style.SUCCESS(f"Done. See {RESOURCES_DIR}/backtest_*.txt"))

    # ----- selections -----
    def _get_ratings(self, cat, earliest, as_of):
        """Ratings rows in [earliest, as_of] for a category, with carry-forward for missing months."""
        rows = [SimpleRating(sid, d, rk) for (sid, d, rk) in
                SARating.objects.filter(type=cat, date__gte=earliest, date__lte=as_of)
                .values_list("sa_stock_id", "date", "rank")]
        for (my, mm) in MISSING_MONTHS:
            miss = date(my, mm, 1)
            if earliest <= miss <= as_of and not any(r.date == miss for r in rows):
                prev = rewind_months(miss, 1)
                rows.extend(SimpleRating(sid, miss, rk) for (sid, rk) in
                            SARating.objects.filter(type=cat, date=prev).values_list("sa_stock_id", "rank"))
        return rows

    def _approach_select(self, approach, cat, as_of):
        kind = approach.kind
        if kind == "decayed":
            # param = the decayed window if an approach overrides it; fallback to self.decay_window.
            window = approach.param if approach.param else self.decay_window
            ratings = self._get_ratings(cat, rewind_months(as_of, window - 1), as_of)
            ids = top_n(score_decayed(ratings, as_of, window))
        elif kind == "momentum":
            ratings = self._get_ratings(cat, rewind_months(as_of, self.momentum_window - 1), as_of)
            ids = top_n(score_momentum(ratings, as_of, self.momentum_window, self.momentum_weight))
        elif kind == "current":
            ratings = self._get_ratings(cat, as_of, as_of)
            ids = top_n({r.sa_stock_id: -r.rank for r in ratings})
        elif kind == "alltime":
            ratings = self._get_ratings(cat, date(2000, 1, 1), as_of)  # all history up to as_of
            ids = top_n(score_alltime(ratings))
        elif kind == "alltime_gated":
            ratings = self._get_ratings(cat, date(2000, 1, 1), as_of)
            scores = score_alltime(ratings)
            current_ids = {r.sa_stock_id for r in self._get_ratings(cat, as_of, as_of)}
            ids = top_n({i: s for i, s in scores.items() if i in current_ids})  # only stocks still ranked now
        elif kind == "decay_curve":
            factors = approach.param
            ratings = self._get_ratings(cat, rewind_months(as_of, len(factors) - 1), as_of)
            ids = top_n(score_decayed(ratings, as_of, decay_factors=factors))
        else:
            raise ValueError(kind)
        return [self.id_to_symbol[i] for i in ids]

    def _month_ranks(self, cat, as_of):
        return {self.id_to_symbol[r.sa_stock_id]: r.rank for r in self._get_ratings(cat, as_of, as_of)}

    def _symbol_universe(self):
        universe = set()
        for cat in CATEGORIES:
            for (y, m) in SIM_MONTHS:
                as_of = date(y, m, 1)
                for approach in self.approaches.values():
                    universe.update(self._approach_select(approach, cat, as_of))
        return sorted(universe)

    # ----- prices -----
    def _get_prices(self, symbols, refetch=False):
        cache = {}
        if not refetch:
            try:
                with open(PRICE_CACHE_PATH) as f:
                    cache = json.load(f)
            except FileNotFoundError:
                cache = {}

        p1 = int(datetime(2023, 9, 1, tzinfo=timezone.utc).timestamp())
        p2 = int(datetime(2026, 5, 31, tzinfo=timezone.utc).timestamp())
        to_fetch = [s for s in symbols if s not in cache]
        for idx, symbol in enumerate(to_fetch, 1):
            cache[symbol] = self._fetch_symbol_monthly(symbol, p1, p2)
            if idx % 20 == 0:
                self.stdout.write(f"    fetched {idx}/{len(to_fetch)}...")
            time.sleep(0.3)
        if to_fetch:
            with open(PRICE_CACHE_PATH, "w") as f:
                json.dump(cache, f)

        price_map = {s: cache.get(s, {}) for s in symbols}
        missing = {s for s in symbols if not price_map[s]}
        return price_map, missing

    def _fetch_symbol_monthly(self, symbol, p1, p2):
        for candidate in (symbol, symbol.replace(".", "-")):
            try:
                resp = requests.get(
                    YAHOO_URL.format(symbol=candidate),
                    params={"period1": p1, "period2": p2, "interval": "1d", "includeAdjustedClose": "true"},
                    headers=YAHOO_HEADERS, timeout=20,
                )
                if resp.status_code != 200:
                    continue
                result = (resp.json().get("chart", {}).get("result") or [None])[0]
                if not result or "timestamp" not in result:
                    continue
                adj = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
                closes = result["indicators"]["quote"][0].get("close")
                series = adj if adj else closes
                monthly = {}
                for ts, px in zip(result["timestamp"], series):
                    if px is None:
                        continue
                    d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
                    mk = month_key(d.year, d.month)
                    if mk not in monthly:
                        monthly[mk] = round(float(px), 4)
                if monthly:
                    return monthly
            except (requests.RequestException, ValueError, KeyError, IndexError):
                continue
        return {}

    @staticmethod
    def _price(price_map, symbol, y, m):
        return price_map.get(symbol, {}).get(month_key(y, m))

    @staticmethod
    def _price_carry(price_map, symbol, y, m):
        series = price_map.get(symbol, {})
        target = month_key(y, m)
        if target in series:
            return series[target]
        earlier = [k for k in series if k <= target]
        return series[max(earlier)] if earlier else None

    # ----- simulation -----
    def _simulate(self, approach, cat, price_map):
        positions = {}   # symbol -> {"shares": float, "age": int}
        cash = 0.0
        equity_curve = []
        holdings_log = {}
        carried = set()
        selected_symbols = set()
        total_sells = 0

        for idx, (y, m) in enumerate(SIM_MONTHS):
            as_of = date(y, m, 1)
            top7 = self._approach_select(approach, cat, as_of)
            selected_symbols.update(top7)

            if idx == 0:
                available = PORTFOLIO_SIZE * DOLLARS_PER_STOCK
                cash += self._buy(positions, top7, available, price_map, y, m)
            else:
                for p in positions.values():
                    p["age"] += 1

                sells = self._sells(approach, positions, top7, cat, as_of)
                total_sells += len(sells)
                proceeds = cash
                cash = 0.0
                for sym in sells:
                    px = self._price_carry(price_map, sym, y, m)
                    if px is not None:
                        if month_key(y, m) not in price_map.get(sym, {}):
                            carried.add(sym)
                        proceeds += positions[sym]["shares"] * px
                    del positions[sym]

                open_slots = PORTFOLIO_SIZE - len(positions)
                entrants = [s for s in top7 if s not in positions][:open_slots]
                cash += self._buy(positions, entrants, proceeds, price_map, y, m)

            value, holdings = self._mark(positions, cash, y, m, price_map, carried)
            equity_curve.append((month_key(y, m), value))
            holdings_log[month_key(y, m)] = holdings

        vy, vm = VALUATION_MONTH
        value, holdings = self._mark(positions, cash, vy, vm, price_map, carried)
        equity_curve.append((exit_month_key(), value))
        holdings_log[exit_month_key()] = holdings

        distinct_held = {s for hl in holdings_log.values() for s, _ in hl if s != "(cash)"}
        return {"equity_curve": equity_curve, "holdings_log": holdings_log,
                "final_value": value, "carried": carried, "selected_symbols": selected_symbols,
                "total_sells": total_sells, "distinct_held": len(distinct_held)}

    def _sells(self, approach, positions, top7, cat, as_of):
        if approach.policy == "strict":
            return [s for s in positions if s not in top7]
        if approach.policy == "rank_band":
            ranks = self._month_ranks(cat, as_of)
            return [s for s in positions if ranks.get(s) is None or ranks[s] > approach.param]
        raise ValueError(approach.policy)

    def _buy(self, positions, buys, available, price_map, y, m):
        """Allocate `available` equally across intended buys. Unpriceable buys leave their share as cash.
        Returns the leftover cash."""
        if not buys:
            return available
        per = available / len(buys)
        leftover = 0.0
        for sym in buys:
            px = self._price(price_map, sym, y, m)
            if px:
                positions[sym] = {"shares": per / px, "age": 0}
            else:
                leftover += per
        return leftover

    def _mark(self, positions, cash, y, m, price_map, carried):
        total = cash
        holdings = []
        for sym, pos in positions.items():
            px = self._price_carry(price_map, sym, y, m)
            if px is None:
                continue
            if month_key(y, m) not in price_map.get(sym, {}):
                carried.add(sym)
            v = pos["shares"] * px
            total += v
            holdings.append((sym, v))
        if cash > 0.01:
            holdings.append(("(cash)", cash))
        return total, holdings

    # ----- reporting -----
    def _ret(self, value):
        initial = PORTFOLIO_SIZE * DOLLARS_PER_STOCK
        return (value / initial - 1) * 100

    @staticmethod
    def _fmt_holdings(holdings):
        return ", ".join(f"{sym} ${v:,.0f}" for sym, v in sorted(holdings, key=lambda x: -x[1]))

    def _write_master(self, results, missing):
        keys = ["decayed", "decay_x2", "momentum_rankband25", "current", "score_alltime", "alltime_gated"]
        labels = {"decayed": "Decayed-old", "decay_x2": "Decayed-new", "momentum_rankband25": "Mom rankband",
                  "current": "Current top7", "score_alltime": "Alltime", "alltime_gated": "Alltime-gated"}
        lines = [f"MASTER COMPARISON - final cumulative return, {PERIOD_LABEL}",
                 f"Rolling top-{PORTFOLIO_SIZE}, ${DOLLARS_PER_STOCK:,.0f}/stock initial, Yahoo adjusted close",
                 f"decayed window={self.decay_window}; momentum window={self.momentum_window}, weight={self.momentum_weight}",
                 "=" * 96, "",
                 f"{'Category':<16} | " + " | ".join(f"{labels[k]:>14}" for k in keys) + " | Best",
                 "-" * 96]
        ret_lists = {k: [] for k in keys}
        wins = {k: 0 for k in keys}
        for cat in CATEGORIES:
            rets = {k: self._ret(results[k][cat]["final_value"]) for k in keys}
            for k in keys:
                ret_lists[k].append(rets[k])
            best = max(keys, key=lambda k: rets[k])
            wins[best] += 1
            lines.append(f"{SARating.TYPES[cat]:<16} | " +
                         " | ".join(f"{rets[k]:>+13.2f}%" for k in keys) + f" | {labels[best]}")
        lines.append("-" * 96)
        n = len(CATEGORIES)
        lines.append(f"{'AVERAGE':<16} | " + " | ".join(f"{sum(ret_lists[k])/n:>+13.2f}%" for k in keys) + " |")
        lines.append(f"{'MEDIAN':<16} | " + " | ".join(f"{_median(ret_lists[k]):>+13.2f}%" for k in keys) + " |")
        lines.append("")
        lines.append("Category wins (best per category): " + ", ".join(f"{labels[k]} {wins[k]}" for k in keys))
        lines.append("")
        lines.append("Approaches:")
        for k in keys:
            lines.append(f"  {labels[k]:<16} = {self.approaches[k].label}")
        if missing:
            lines += ["", f"Symbols with no price data ({len(missing)}), held as cash when selected:",
                      "  " + ", ".join(sorted(missing))]
        with open(f"{RESOURCES_DIR}/backtest_comparison.txt", "w") as f:
            f.write("\n".join(lines) + "\n")

    def _write_regime_report(self, results):
        """Turnover + downturn behaviour on the aggregate (all 8 categories combined) portfolio."""
        keys = ["decayed", "decay_x2", "momentum_rankband25", "current", "score_alltime", "alltime_gated"]
        labels = {"decayed": "Decayed-old", "decay_x2": "Decayed-new", "momentum_rankband25": "Mom rankband",
                  "current": "Current top7", "score_alltime": "Alltime", "alltime_gated": "Alltime-gated"}
        month_labels = [lbl for lbl, _ in results["decayed"][CATEGORIES[0]]["equity_curve"]]
        # Aggregate equity per approach = sum of the 8 category portfolios.
        agg = {k: [sum(results[k][cat]["equity_curve"][i][1] for cat in CATEGORIES)
                   for i in range(len(month_labels))] for k in keys}
        # Month-over-month return per approach.
        mom = {k: [agg[k][i] / agg[k][i - 1] - 1 for i in range(1, len(month_labels))] for k in keys}
        # "Down-months" = months where the average MoM across approaches was negative.
        down_idx = [i for i in range(len(month_labels) - 1)
                    if sum(mom[k][i] for k in keys) / len(keys) < 0]

        n = len(CATEGORIES)
        lines = [f"REGIME & TURNOVER ANALYSIS - {PERIOD_LABEL}",
                 f"Aggregate portfolio = all {n} categories combined "
                 f"(${PORTFOLIO_SIZE * DOLLARS_PER_STOCK * n:,.0f} initial)",
                 "Turnover = avg positions sold per rebalance (lower = fewer taxable events / better for long-term hold)",
                 "=" * 92, "",
                 f"{'Approach':<16} | {'Final ret':>10} | {'Max drawdown':>13} | {'Sells/mo':>9} | "
                 f"{'Distinct held':>13} | {'Down-mo ret':>12}",
                 "-" * 92]
        for k in keys:
            final_ret = (agg[k][-1] / agg[k][0] - 1) * 100
            mdd = _max_drawdown(agg[k])
            avg_sells = sum(results[k][cat]["total_sells"] for cat in CATEGORIES) / n / (len(SIM_MONTHS) - 1)
            distinct = sum(results[k][cat]["distinct_held"] for cat in CATEGORIES) / n
            down_ret = 1.0
            for i in down_idx:
                down_ret *= (1 + mom[k][i])
            down_ret = (down_ret - 1) * 100
            lines.append(f"{labels[k]:<16} | {final_ret:>+9.1f}% | {mdd:>+12.1f}% | {avg_sells:>9.1f} | "
                         f"{distinct:>13.1f} | {down_ret:>+11.1f}%")
        lines.append("")
        lines.append(f"Down-months (aggregate fell, {len(down_idx)} of {len(month_labels) - 1}): "
                     + ", ".join(month_labels[i + 1] for i in down_idx))
        lines.append("")
        lines.append("Notes:")
        lines.append("  - 'Down-mo ret' = compounded return ACROSS just the down-months above. Less negative = better")
        lines.append("    drawdown protection. This is the closest proxy we have to downturn behaviour, but these")
        lines.append("    are shallow dips in a bull market -- NOT a real bear. Treat as suggestive, not conclusive.")
        lines.append("  - 'Sells/mo' and 'Distinct held' measure turnover: lower = fewer taxable events, better for")
        lines.append("    a buy-and-hold / tax-deferred portfolio.")
        with open(f"{RESOURCES_DIR}/backtest_regime_turnover.txt", "w") as f:
            f.write("\n".join(lines) + "\n")

    def _comparison_lines(self, keys, labels, results, cats=None):
        """Per-category return table + AVERAGE/MEDIAN + aggregate metrics block (drawdown/turnover/down-mo)."""
        cats = cats or CATEGORIES
        n = len(cats)
        width = 16 + 16 * len(keys)
        lines = [f"{'Category':<16} | " + " | ".join(f"{labels[k]:>13}" for k in keys), "-" * width]
        ret_lists = {k: [] for k in keys}
        for cat in cats:
            rets = {k: self._ret(results[k][cat]["final_value"]) for k in keys}
            for k in keys:
                ret_lists[k].append(rets[k])
            lines.append(f"{SARating.TYPES[cat]:<16} | " + " | ".join(f"{rets[k]:>+12.1f}%" for k in keys))
        lines.append("-" * width)
        lines.append(f"{'AVERAGE':<16} | " + " | ".join(f"{sum(ret_lists[k]) / n:>+12.1f}%" for k in keys))
        lines.append(f"{'MEDIAN':<16} | " + " | ".join(f"{_median(ret_lists[k]):>+12.1f}%" for k in keys))
        lines.append("")

        month_labels = [lbl for lbl, _ in results[keys[0]][cats[0]]["equity_curve"]]
        agg = {k: [sum(results[k][cat]["equity_curve"][i][1] for cat in cats)
                   for i in range(len(month_labels))] for k in keys}
        mom = {k: [agg[k][i] / agg[k][i - 1] - 1 for i in range(1, len(month_labels))] for k in keys}
        down_idx = [i for i in range(len(month_labels) - 1) if sum(mom[k][i] for k in keys) / len(keys) < 0]
        lines.append(f"{'Metric':<16} | " + " | ".join(f"{labels[k]:>13}" for k in keys))
        lines.append("-" * width)
        lines.append(f"{'Max drawdown':<16} | " + " | ".join(f"{_max_drawdown(agg[k]):>+12.1f}%" for k in keys))
        lines.append(f"{'Sells/mo':<16} | " + " | ".join(
            f"{sum(results[k][cat]['total_sells'] for cat in cats) / n / (len(SIM_MONTHS) - 1):>13.1f}"
            for k in keys))
        lines.append(f"{'Distinct held':<16} | " + " | ".join(
            f"{sum(results[k][cat]['distinct_held'] for cat in cats) / n:>13.1f}" for k in keys))
        down_rets = {}
        for k in keys:
            r = 1.0
            for i in down_idx:
                r *= (1 + mom[k][i])
            down_rets[k] = (r - 1) * 100
        lines.append(f"{'Down-mo ret':<16} | " + " | ".join(f"{down_rets[k]:>+12.1f}%" for k in keys))
        return lines

    def _write_weighted_report(self, results):
        """Re-weight the per-category results to approximate Marco's tech-heavy real allocation."""
        keys = ["decay_x2", "score_alltime", "alltime_gated", "current", "momentum_rankband25"]
        labels = {"decay_x2": "Decayed(new)", "score_alltime": "All-time", "alltime_gated": "Alltime-gated",
                  "current": "Current-7", "momentum_rankband25": "Mom rankband"}
        w = CATEGORY_WEIGHTS
        total_w = sum(w.values())
        n = len(CATEGORIES)
        month_labels = [lbl for lbl, _ in results["decay_x2"][CATEGORIES[0]]["equity_curve"]]

        lines = [f"CATEGORY-WEIGHTED ESTIMATE - {PERIOD_LABEL}",
                 "Approximates Marco's real allocation: tech-heavy, light on financial/communication.",
                 "Weights -> " + ", ".join(f"{SARating.TYPES[c]} x{w[c]:g}" for c in CATEGORIES),
                 "Equal-wt = simple average of all 8 categories (what the other reports show).",
                 "Tech-wt  = weighted average using the weights above (your actual tilt).",
                 "=" * 70, "",
                 f"{'Approach':<16} | {'Equal-wt ret':>13} | {'Tech-wt ret':>13} | {'Tech-wt maxDD':>14}",
                 "-" * 66]
        for k in keys:
            eq = sum(self._ret(results[k][c]["final_value"]) for c in CATEGORIES) / n
            tw = sum(w[c] * self._ret(results[k][c]["final_value"]) for c in CATEGORIES) / total_w
            wcurve = [sum(w[c] * results[k][c]["equity_curve"][i][1] for c in CATEGORIES)
                      for i in range(len(month_labels))]
            lines.append(f"{labels[k]:<16} | {eq:>+12.1f}% | {tw:>+12.1f}% | {_max_drawdown(wcurve):>+13.1f}%")
        lines += ["",
                  "Caveats:",
                  "  - Weights are an ESTIMATE of your typical allocation -- edit CATEGORY_WEIGHTS to match reality.",
                  "  - STATIC approximation: does NOT model your news-driven rotation (cutting tech in bad months).",
                  "    That rotation would likely LOWER the tech-wt drawdown below what's shown here.",
                  "  - Your defensive rotation targets (Utility, Consumer Staples) aren't among the 8 simulated",
                  "    categories, so this can't capture the defensive switch even in principle.",
                  "  - Tech-heavy weighting boosted returns because tech BOOMED this period; in a tech downturn it",
                  "    would amplify losses -- which is exactly why you de-risk tech on bad news."]
        with open(f"{RESOURCES_DIR}/backtest_weighted.txt", "w") as f:
            f.write("\n".join(lines) + "\n")

    def _write_subset_report(self, results):
        """Marco's three most-used categories only: Overall, Quant, Technology."""
        cats = ["top_rated_overall", "top_quant", "top_technology"]
        keys = ["decayed", "decay_x2", "current", "score_alltime", "alltime_gated"]
        labels = {"decayed": "Decayed-old", "decay_x2": "Decayed-new", "current": "Current-7",
                  "score_alltime": "All-time", "alltime_gated": "Alltime-gated"}
        lines = [f"FAVOURITE-CATEGORIES SUBSET - {PERIOD_LABEL}",
                 "Only the 3 categories Marco uses most: Overall, Quant, Technology.",
                 "Decayed-old = linear [1.0, 0.667, 0.333];  Decayed-new = exponential [1.0, 0.5, 0.25] (production).",
                 "Aggregate metrics (drawdown / turnover / down-mo) are over these 3 categories only.",
                 "=" * 96, ""]
        lines += self._comparison_lines(keys, labels, results, cats=cats)
        with open(f"{RESOURCES_DIR}/backtest_subset_oqt.txt", "w") as f:
            f.write("\n".join(lines) + "\n")

    def _write_by_category_report(self, results):
        """One table per favourite category (Technology, Quant, Overall), all live algorithms as rows."""
        d = PORTFOLIO_SIZE * DOLLARS_PER_STOCK             # 17,500 (7 positions)
        # (key, label, initial capital). All live approaches; dead ones excluded.
        specs = [
            ("decayed", "Decayed-old [1,.667,.333]", d),
            ("decay_x2", "Decayed-new [1,.5,.25]", d),
            ("momentum_rankband25", "Momentum rank-band", d),
            ("current", "Current top-7", d),
            ("score_alltime", "All-time score", d),
            ("alltime_gated", "All-time gated", d),
        ]
        cats = [("top_technology", "TECHNOLOGY"), ("top_quant", "QUANT"), ("top_rated_overall", "OVERALL")]
        out = [f"BY-CATEGORY ALGORITHM COMPARISON - {PERIOD_LABEL}",
               "One table per category, all live algorithms, sorted by return (best first).",
               "All start at $17,500 / 7 positions. Returns = % of own capital.",
               ""]
        for cat, name in cats:
            out += ["=" * 62, name, "=" * 62,
                    f"{'Algorithm':<26} | {'Return':>9} | {'Max DD':>8} | {'Sells/mo':>8}",
                    "-" * 62]
            rows = []
            for key, label, init in specs:
                r = results[key][cat]
                ret = (r["final_value"] / init - 1) * 100
                dd = _max_drawdown([v for _, v in r["equity_curve"]])
                sells = r["total_sells"] / (len(SIM_MONTHS) - 1)
                rows.append((ret, label, dd, sells))
            for ret, label, dd, sells in sorted(rows, key=lambda x: -x[0]):
                out.append(f"{label:<26} | {ret:>+8.1f}% | {dd:>+7.1f}% | {sells:>8.1f}")
            out.append("")
        with open(f"{RESOURCES_DIR}/backtest_by_category.txt", "w") as f:
            f.write("\n".join(out) + "\n")

    def _write_detail_report(self, results):
        """Detailed side-by-side: top contenders for Tech/Quant/Overall, with calendar-period returns."""
        keys = ["decayed", "decay_x2", "score_alltime", "alltime_gated"]
        labels = {"decayed": "Decayed-old", "decay_x2": "Decayed-new[.5,.25]",
                  "score_alltime": "All-time", "alltime_gated": "All-time gated"}
        cats = [("top_technology", "TECHNOLOGY"), ("top_quant", "QUANT"), ("top_rated_overall", "OVERALL")]
        init = PORTFOLIO_SIZE * DOLLARS_PER_STOCK
        # Calendar-period returns (growth within each span), using the equity value at each boundary month.
        periods = [("'23 Nov-Dec", "2023-11", "2024-01"),
                   ("2024", "2024-01", "2025-01"),
                   ("2025", "2025-01", "2026-01"),
                   ("'26 Jan-May", "2026-01", exit_month_key())]
        out = [f"DETAILED COMPARISON - {PERIOD_LABEL}",
               "All-time vs All-time-gated vs Decayed-new[1.0,0.5,0.25] vs Decayed[1.0,0.33,0.11].",
               "Per category: summary metrics + per-calendar-period returns (growth within each span).",
               "All four = 7 stocks / $17,500. No look-ahead: each month's score uses only data up to that month.",
               ""]
        for cat, name in cats:
            out += ["=" * 108, name, "=" * 108,
                    f"{'Approach':<20} | {'Final':>8} | {'MaxDD':>7} | {'Sells/mo':>8} | "
                    + " | ".join(f"{p[0]:>11}" for p in periods),
                    "-" * 108]
            for k in keys:
                r = results[k][cat]
                curve = {mk: v for mk, v in r["equity_curve"]}
                final = (r["final_value"] / init - 1) * 100
                dd = _max_drawdown([v for _, v in r["equity_curve"]])
                sells = r["total_sells"] / (len(SIM_MONTHS) - 1)
                pers = []
                for _, s, e in periods:
                    if s in curve and e in curve and curve[s]:
                        pers.append(f"{(curve[e] / curve[s] - 1) * 100:>+10.1f}%")
                    else:
                        pers.append(f"{'n/a':>11}")
                out.append(f"{labels[k]:<20} | {final:>+7.1f}% | {dd:>+6.1f}% | {sells:>8.1f} | " + " | ".join(pers))
            out.append("")
        with open(f"{RESOURCES_DIR}/backtest_detail_oqt.txt", "w") as f:
            f.write("\n".join(out) + "\n")

