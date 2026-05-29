# Simulations Guide — for Claude

This is the detailed handoff doc for whichever Claude session picks up the
quant simulation work later. The user (Marco) has a short README.md alongside
this file; this one is the technical guide that lets you re-engage without
re-deriving the whole project history.

A complementary memory entry exists at
`~/.claude/projects/E--DEV-Stocks-Watcher/memory/project_momentum_backtest.md`
which is auto-loaded and summarises the decision history in chronological
"follow-up" blocks. Read it first — this guide is the **how**, the memory is
the **why**.

---

## 1. What the project is doing

The user imports monthly **Seeking Alpha** ranking dumps (top 100 by category)
into `apps.quant.models.SARating`. He runs a TFSA portfolio that picks the
top-7 stocks each month using one of several **scoring algorithms** that turn
the historical ranks into a per-stock score:

- `sa/score` — all-time cumulative `sum(101 − rank)`
- `sa/score_decayed` — recent score, exponential decay `0.5^i` over 3 months
  (production curve `[1.0, 0.5, 0.25]` after the upgrade in follow-up 8)
- `sa/score_momentum` — base + 2 × momentum, designed to catch rising stars

(A `sa/score_consistency` view existed during the experiment phase and was
removed when it tested out as mechanically the weakest — see the dropped-
approach list and the memory file for the full story.)

The backtest in `apps/quant/management/commands/backtest_scores.py` simulates
a rolling top-7 portfolio for each algorithm across 8 of the 14 SA categories,
producing the reports in this folder.

## 2. Code map

- **Command**: `apps/quant/management/commands/backtest_scores.py`
  (Django requires management commands to live there; can't move it.)
- **Outputs**: `quant_simulations/` (this folder). `RESOURCES_DIR = "quant_simulations"`.
- **Memory (decision history)**: `~/.claude/projects/E--DEV-Stocks-Watcher/memory/project_momentum_backtest.md`
- **Project README** for the score views: `README.md` at repo root.

### Key constants / pieces
- `CATEGORIES` — the 8 SA categories simulated (Overall, Quant, Growth, Value,
  Tech, Materials, Communication, Financial). Sectors like Utility / Consumer
  Staples are NOT in here (the user mentioned those as defensive rotation
  targets, but no data was imported).
- `SIM_MONTHS` — generated from `SIM_START = (2023, 11)` to `SIM_END = (2026, 4)`.
  First buy = Nov 2023 (first month with a full 4-month momentum window;
  ratings start 2023-08). Final mark-to-market = May 2026.
- `MISSING_MONTHS = {(2024, 11)}` — ratings for Nov 2024 are missing. Handled
  by carrying Oct 2024 forward as synthetic ratings (in-memory only). Prices
  for that month are real — only ratings are missing.
- `PORTFOLIO_SIZE = 7`, `DOLLARS_PER_STOCK = 2500.0`.
- `CATEGORY_WEIGHTS` — approximation of Marco's real-life tech-heavy
  allocation, used only by `_write_weighted_report`. Tweak freely.

### Phases of `handle()`
- **A — selections + universe**: for every (cat, month, approach), call
  `_approach_select` to determine which symbols would be picked. Union ⇒
  symbol universe to fetch prices for.
- **B — prices**: Yahoo `chart` v8 API (`query1.finance.yahoo.com`), no key,
  adjusted closes. Per-symbol cached to `_backtest_price_cache.json` (one
  call per symbol, full window 2023-09 → 2026-05). `--refetch` ignores cache.
  Throttled 0.3s between calls.
- **C — simulate** every approach for every category: rolling top-7,
  keep-survivors / replace-dropouts, `$2,500/stock` initial.
- **D — reports**: 7 text reports into this folder.

### Live approaches (in `self.approaches`)
| Key | Description | Notes |
| --- | --- | --- |
| `decayed` | Linear [1, 0.667, 0.333] (old prod) | Kept for old-vs-new reference |
| `decay_x2` | Exponential [1, 0.5, 0.25] | **Current production curve** |
| `momentum_rankband25` | Enter momentum top-7, exit on rank>25 | Best momentum variant; trails core |
| `current` | This month's rank 1-7, raw | Dead-simple baseline; high return, big drawdowns |
| `score_alltime` | Cumulative `sum(101 − rank)` | Long-term winner; lowest turnover |
| `alltime_gated` | All-time, gated to currently-ranked | Corpse-fixed; great in Quant, hurts Overall |

### Dropped approaches (do NOT add back without strong reason)
- `momentum` (strict, naive) — worst everywhere
- `momentum_minhold3` — double-edged, big losses
- `decayed_hysteresis` — hurt returns, modest turnover saving worthless in TFSA
- `decayed_reweight` (sell-all-and-rebuy-equal each month) — worse return + 2× turnover
- `blend` (z-score decayed + 0.5 × z-score momentum) — never beat decayed alone
- `decay_x3` / `decay_x4` (steeper curves) — too steep, lose returns
- `decayed2` (2-month window) — worst window
- `decayed5` — lost to 3-month in 6 of 8 categories; only Tech outlier saved its mean
- `decayed12` — confounded (partial history pre-Aug-2024; bull-market stickiness);
  barely "decayed" anymore (1.5 sells/mo, basically all-time-lite)
- `consistency` (3-mo mean − 0.5×vol) — worst on every aggregate metric after the
  6→3-month change; useful as a steady-names *lens* but mechanically weak
- `hybrid` (decayed-7 + 8th "current #1" satellite) — confirmed negative;
  the satellite is just concentrated current-7, lottery returns with worse drawdown

If a yearly re-run with new (especially bear-market) data shows a dropped
approach winning, that's a regime shift signal worth investigating — but on
the bull data we have, none of these warrant re-adding.

## 3. Methodology — the things that matter

**No look-ahead.** `_get_ratings(cat, earliest, as_of)` filters
`date <= as_of`. Every score at month M only uses ratings from months ≤ M.
The all-time score accumulates history walk-forward (4 months at Nov 2023,
growing to 33 by May 2026). This was explicitly verified.

**The 2024-11 ratings gap.** Carried-forward from Oct 2024. Two virtues:
(a) the Nov rebalance is a no-op "hold" because picks are unchanged from
Oct; (b) it avoids fake momentum slopes (a real zero-month would simulate
every stock dropping to rank 101 then recovering, polluting the slope-based
momentum score for Dec/Jan/Feb 2025). Prices for Nov 2024 are real.

**List depth varies by category.** Major finding (follow-up 11): Overall
list has only ~46 names/month, Quant ~100, Tech ~97. Drives why gating
(filter to currently-ranked) helps Quant but hurts Overall — see memory.

**Hybrid uses different initial capital.** When/if you re-introduce the
hybrid sleeve (don't — it's dead), remember it starts at $20,000 (8 × $2,500)
vs $17,500 for the standard 7-stock approaches. The reports that contain it
must use the right denominator. The current code doesn't compute hybrid;
this is a note in case future you considers it again.

## 4. How to read the reports

- **Mean vs Median is the most important distinction.** When mean ≫ median,
  the average is being inflated by one or two fat-tail categories (usually
  Tech +500-1000%). Median = the typical category; pay attention to both.
- **Max drawdown is computed on the aggregate equity curve** (sum across the
  8 categories combined) for `regime_turnover` and `variants`, but on
  **single-category** equity curves in `by_category` and `detail_oqt`. The
  single-category drawdowns are bigger because there's no diversification.
- **Down-mo ret** = compounded return through just the months when the
  aggregate fell. Closest proxy we have to "how this would behave in a
  downturn", but the dips in 2023-08 → 2026-05 are all shallow V-shapes.
  A real bear is the missing test.
- **Sells/mo and Distinct held** are the turnover metrics. All-time has
  the lowest turnover (~0.6 sells/mo) — that's how it compounds.
- **Down-months in the data** are roughly: 2024-05, 07, 08; 2025-03, 04,
  05, 08, 11, 12; 2026-04. None sustained.

## 5. Marco's two portfolios (drives recommendations)

1. **Long-term taxable** — buy-and-hold for years to avoid capital gains
   tax → wants minimum turnover. Best fit: **all-time score** (lowest
   turnover, highest median over 30 months) or **gated all-time** for the
   corpse-protected version (especially relevant over the 20-year horizon
   where a former champion *will* eventually collapse).

2. **Monthly TFSA** — tax-free, swapped monthly for current strength →
   wants responsiveness. Best fit: **decayed-new (`decay_x2`)** at 3-month
   exponential curve [1, 0.5, 0.25]. He's tech-heavy (~7 tech + 1 each of
   quant/overall/growth/materials) and cuts tech on bad news as a
   discretionary defensive rotation we can't simulate.

## 6. What to do at the annual re-run

When fresh monthly data arrives (~12 new monthly dumps):

1. **Verify the data import** by querying SARating for the new months. Spot
   the latest month present and any new gaps.
2. **Update `SIM_END` and `VALUATION_MONTH`** in `backtest_scores.py` to
   extend the window through the new latest month. Also extend
   `PRICE_END` in `_get_prices` for the price fetch window.
3. **Update `MISSING_MONTHS`** if new gaps appeared.
4. **Run** with `--refetch` (the timeline changed; cache needs new months).
   First run ~5-10 minutes for the fetch.
5. **Compare**:
   - Did the leaderboard in `backtest_comparison.txt` shuffle? If decayed-new
     and all-time are still top, the bull continued. If momentum-rankband or
     decayed_5/12 climb to the top, a regime might be shifting.
   - **Did any approach show a much bigger drawdown?** `regime_turnover.txt`
     max-drawdown column. A real bear in the new data is the experiment we
     couldn't run originally — this is the headline check.
   - In `by_category.txt`, did the tech-trend stickiness break? If
     decayed_5/12 stop crushing in Tech, that's a tech-regime change.
6. **Update the memory file** (`project_momentum_backtest.md`) with a new
   "Follow-up N" entry summarising what's different.

## 7. Open questions to revisit in a bear

These were untestable on the original 2023-08 → 2026-05 bull-only data:

- Does momentum-rankband finally earn its keep in a downturn by rotating
  out of decliners (its theoretical advantage)?
- Does all-time's stickiness backfire when a previously-dominant name
  collapses (the "hold a corpse" risk that gated all-time exists to prevent)?
- Does gated all-time start helping Overall too once the shallow ~46-list
  starts ejecting genuinely-failing names instead of temporary dippers?
- Does the user's defensive rotation pattern (cutting tech on bad news)
  become visibly valuable in the aggregate equity curve?

### 7a. Long-window experiment (24-month variants) — re-offer when data allows

Marco was curious whether a **24-month capped all-time** (uniform window) or a
**24-month decayed score** (e.g. `0.9 ** i`) would beat the existing approaches —
the appeal being "natural corpse expiry after 24 months without the binary gate."
I ran it ad-hoc in May 2026 with the caveat that only ~10 of 30 sim months
exercised a full 24-month window (data started 2023-08, sim started 2023-11).
Result was inconclusive: both variants beat existing approaches on **mean** but
Tech-outlier-driven; **median** didn't follow, and the partial-window /
bull-market-stickiness confound makes the result unreliable.

**Re-offer this experiment when:** the data has roughly 4+ years of history
AND ideally a real correction/bear in the window (so the full 24-month period
gets stressed across regimes, not just a uniform bull).

**To run it again** (no code changes needed — paste the python into
`python manage.py shell` via heredoc + `exec(r"""...""")` wrapper to bypass
REPL block-rules): the snippet defines `select_capped` (uniform weights,
24-month window) and `select_dec24` (exponential `0.9 ** i`, 24-month window),
both reusing the existing `score_decayed` / `top_n` / price-cache machinery.
The previous run's snippet is recoverable from the conversation thread on
2026-05-28; if not, reconstruct from `_simulate` in `backtest_scores.py` —
the only new piece is a `rwind_long(as_of, n)` helper that handles
months_to_rewind > 11 (the production `rewind_months` only does ONE +12
correction so it breaks past 11).

**Tell Marco when re-offering:** "Your 24-month-window question from 2026-05.
Data window is now big enough to test it properly. Want me to run it?"

## 8. Things that broke me / would catch you

- **Don't move the management command file**. Django *requires* it to live at
  `apps/quant/management/commands/`. The output dir can move freely (now
  `quant_simulations/`).
- **`Approach.param` is overloaded** — it's the decay window for window-sweep
  approaches (decayed5 = 5), the rank-band threshold for rank-band momentum
  (momentum_rankband25 = 25), and `None` otherwise. `_approach_select` and
  `_sells` read it per kind/policy. Don't conflate.
- **`get_distance_in_months` only allows months_to_rewind ≤ 11** — it
  applies a single +12 correction. If a future approach uses a window > 12,
  generalize the helper first.
- **Symbol fallback for Yahoo**: `_fetch_symbol_monthly` retries with
  `symbol.replace('.', '-')` because Yahoo uses dashes (BRK-B, not BRK.B).
  This catches most class-share misses.
- **Missing symbols stay as cash** in the simulation — `_buy` returns
  leftover cash for unpriceable buys, `_mark` includes cash in total. The
  reports include a coverage list at the bottom of `backtest_comparison.txt`.
- **The price cache is `{symbol: {YYYY-MM: float}}`** — monthly first-trading-day
  closes only, not full daily series. Sufficient for monthly rebalancing;
  if you ever need daily, the cache schema must change.

## 9. If the user wants new experiments

Approaches go in `self.approaches`. To add a new score type:
1. Add an `Approach(...)` to the dict (pick a unique `kind` string).
2. Add a branch in `_approach_select` for that kind, returning a list of
   symbols (top 7 by your score).
3. If it's purely a new SELECTION method (no portfolio-construction trick),
   that's enough — `_simulate` will handle it via `strict` policy.
4. If it needs a different exit rule, add a `policy` branch in `_sells`.
5. Add the key to the relevant report `keys` lists (or write a new report).

## 10. Production cron implications

The backtest's findings were back-applied to production:
- `CompiledSAScoreDecayed.DECAY_BASE = 0.5` (was linear, now exponential).
  See `compile_sa_score_decayed` in `apps/quant/views/cron.py`.
- `CompiledSAScoreConsistency` was experimented with (`sa/score_consistency`
  view + cron) and then **removed from the project entirely** after the
  backtest showed it was mechanically the weakest performer on every
  aggregate metric. Migration `0004` drops the table.

If the yearly re-run shifts those recommendations, the production crons are
where you'd update — and the user would need to clear the relevant compiled
table and re-run the cron, since the cron skips already-compiled types.

## 11. Portability / Git

The price cache `_backtest_price_cache.json` (~500 KB) is committed to the
repo — it is NOT gitignored. So a clean clone on another machine can run the
backtest immediately without re-fetching, as long as the simulation timeline
hasn't been extended. If `SIM_END` / `PRICE_END` change, delete the cache and
re-run with `--refetch`.
