# Quant simulations

Backtest outputs comparing the SA scoring algorithms (decayed, all-time, etc.)
on a rolling top-7 portfolio. Re-run yearly with fresh data to see whether the
algorithm rankings change as the market regime changes.

## The six algorithms, in plain English

Ordered from "most reactive to this month's moves" to "most patient":

1. **Current top-7** — *no algorithm at all.*
   - **How**: Buy this month's rank 1-7. Next month, sell anything that
     fell out, buy whatever replaced them.
   - **Strength**: Surprisingly competitive returns; the dead-simple
     baseline ("is anything *actually* beating just-hold-the-top-list?").
   - **Catch**: **Biggest drawdowns** of any approach — chases every fresh
     #1, including flukes.

2. **Decayed-new `[1.0, 0.5, 0.25]`** — *current production
   `sa/score_decayed`.*
   - **How**: Sum each stock's score over the last 3 months — this month
     at full weight, last month at half, two months ago at a quarter. A
     stock has to keep showing up to keep its score.
   - **Strength**: Responsive without chasing flukes — the right fit for
     your **monthly TFSA**.

3. **Decayed-old `[1.0, 0.667, 0.333]`** — *previous production curve.*
   - **How**: Same 3-month window as decayed-new but a gentler ramp-down
     (older months still carry meaningful weight).
   - **Why kept**: Reference point so you can confirm the new curve is
     still outperforming.

4. **Momentum rank-band** — *catches rising stocks; holds while they stay
   strong.*
   - **How**: Buy stocks with strong momentum (a separate score that
     rewards rising ranks). Hold each until its actual rank slips past
     25, then sell.
   - **Strength**: Best of the momentum variants we tested.
   - **Catch**: **Consistently trails** the steady scores in our
     bull-only data.
   - **Worth watching**: Momentum is *supposed* to shine in downturns —
     re-run is when we'd find out.

5. **All-time score** — *the long-term winner.*
   - **How**: Sum of `(101 - rank)` over **every** month a stock has been
     ranked, no decay. Rewards long, persistent rankings.
   - **Strengths**: **Lowest turnover** (~0.6 trades/month) and **highest
     median return** in our data.
   - **Catch — "corpse" risk**: A former champion that drops out of the
     rankings *keeps* its banked score and stays pinned at the top forever.
     Doesn't show up in bull data, but matters over a 20-year horizon.

6. **All-time gated** — *all-time score with a corpse filter.*
   - **How**: Same as all-time, but only stocks still in **this month's**
     top-100 list are eligible to be picked.
   - **Strength**: **Best risk-adjusted** approach in Quant — the gate
     catches genuinely failing stocks.
   - **Catch**: **Hurts in Overall** — that list is only ~46 names deep,
     so the gate ejects temporary dippers that rebound. (See "Practical
     fit" for which category gets which version.)

**Practical fit:**
- **Monthly TFSA** (monthly swap, tax-free): **Decayed-new**.
- **Long-term taxable account** (years without touching, few transactions):
  - **All-time gated** for the *Top Quant* category — the gate correctly
    drops genuinely failing stocks in a list this deep (~100 names).
  - **All-time (non-gated)** for the *Top Overall* category — the Overall
    list is much shallower (~46 names), so the gate ejects temporary
    dippers that rebound, hurting returns.
- **Current top-7** is your "is anything *actually* beating dead-simple?"
  reality check.

## What's in here

| File | What it tells you |
| --- | --- |
| `backtest_comparison.txt` | Master table — every algorithm × every category, mean + median |
| `backtest_by_category.txt` | One table per favourite category (Tech / Quant / Overall), algorithms sorted by return |
| `backtest_detail_oqt.txt` | Top contenders for Tech/Quant/Overall with per-year breakdowns |
| `backtest_subset_oqt.txt` | Same algorithms aggregated over just your three favourite categories |
| `backtest_weighted.txt` | Your tech-heavy allocation applied to each algorithm |
| `backtest_regime_turnover.txt` | Drawdown, turnover, and behaviour during down-months |
| `_backtest_price_cache.json` | Cached Yahoo prices (don't delete — re-runs reuse it) |

## How to re-run it (every year, say each May or June)

1. Make sure your fresh monthly data dumps are imported up to the latest month.
2. From the project root, run:
   ```
   python manage.py backtest_scores
   ```
   First run after a new year of data will fetch prices for any new symbols
   (~2-3 minutes). Subsequent runs hit the cache and finish in seconds.
3. Open `backtest_comparison.txt` first — it's the headline. Then
   `backtest_by_category.txt` for your three favourite categories.

If you ever **extend the timeline** (e.g. by importing older months), delete
the cache so it refetches with the wider date window:
```
rm quant_simulations/_backtest_price_cache.json
python manage.py backtest_scores --refetch
```

## What to look for in the re-run

- **Has the algorithm ranking changed?** If decayed-new and all-time are
  still on top, the regime hasn't shifted meaningfully. If something else
  climbs (especially the momentum variant in a downturn), that's the new
  signal.
- **Did drawdowns get bigger?** Aggregate max drawdown in
  `backtest_regime_turnover.txt` tells you whether the new data included
  a real correction — which is the test we couldn't run with a pure bull
  history.
- **Tech vs everything else** — `backtest_by_category.txt` shows whether
  the tech-trend stickiness still favours all-time-style scores there.

## Deeper context

For the full history of decisions (what we tried, what we dropped, why), see
`SIMULATIONS_GUIDE.md` in this folder — that's the detailed handoff for
Claude to pick up the work in the future without re-litigating everything.
