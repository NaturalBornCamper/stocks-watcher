# Stocks Watcher

A Django app for tracking Seeking Alpha stock rankings over time and turning the
monthly rank dumps into something more actionable than a single month's list.

> This README will grow over time. For now it documents the score-compilation
> algorithms used by the `sa/score*` views. Project-wide setup, other quant
> views, alerts, etc. will be added as those parts mature.

---

## How the rank data looks

Each month we import a Seeking Alpha "top 100" dump per category (Overall,
Quant, Dividend, Growth, Healthcare, ...). Per stock per month per category we
store a `rank` from 1 (best) to 100 (still in the top, but barely).

A few conventions used throughout the scoring code:

- **`rank = 101`** is a sentinel meaning *"this stock was not in the top 100
  that month"*. It's not a real rank, just a placeholder that lets us reason
  about gaps in a stock's history without special-casing them everywhere.
- **`value = max(0, 101 - rank)`** is the per-month "points" version of the
  rank: rank 1 → 100 points, rank 100 → 1 point, rank 101 → 0 points.
  Used by every score compilation.

A stock's history is therefore a sequence of monthly values, e.g.
`[100, 97, 92, 0, 0]` = newest month at rank 1, then 4, then 9, then not in the
top 100 for the two months before that.

---

## The three scoring views

All three live at `apps/quant/views/score.py` and share the same display
template. They differ only in how they collapse a stock's monthly history into
a single number.

| URL | Model | Question it answers |
| --- | --- | --- |
| `sa/score` | `CompiledSAScore` | *"How often and how highly has this stock ever ranked?"* (all-time popularity) |
| `sa/score_decayed` | `CompiledSAScoreDecayed` | *"Same, but only counting the last few months, with recent months worth more."* (recent popularity) |
| `sa/score_momentum` | `CompiledSAScoreMomentum` | *"Is this stock rising or falling right now?"* (catch rising stars, avoid decliners) |

### 1. `sa/score` — all-time score

The simplest one. For every month the stock appears in the rankings, add
`101 - rank` to its score.

```
score = sum(101 - rank for every month the stock was in the top 100)
```

A stock that's been at rank 1 for 50 months scores 50 × 100 = 5000. A stock
that ranked 80th once scores 21.

**What it's good for:** "famous" stocks — anything with a long history of
appearing in the rankings. **What it ignores:** when those appearances
happened. A stock that was great five years ago and has been gone since looks
identical to one that's been great every month including this one.

### 2. `sa/score_decayed` — recent score

Same idea, restricted to the last N months (default 3), with each month's
contribution multiplied by a decay factor so recent months count more.

```
decay_factors = [1.0, 0.5, 0.25]         # DECAY_BASE^i, for N = 3 months
score = sum((101 - rank_i) * decay_factor_i)
```

The decay factors are `DECAY_BASE ** i` for i in `0..N-1` (default `DECAY_BASE
= 0.5`), so the most recent month is full weight and older months fall off
exponentially. Months outside the window aren't counted at all. (This
exponential curve replaced an older linear `(N - i) / N` curve — a backtest
showed the steeper `[1.0, 0.5, 0.25]` gave higher returns at the same
drawdown, surfacing fresh winners a touch faster.)

**What it's good for:** "what's hot right now". A stock has to keep showing up
recently to keep its score. **What it ignores:** *direction* — a stock that's
been stable at rank 5 looks the same as one that just climbed from rank 80 to
rank 5.

### 3. `sa/score_momentum` — rising-stars score

The new view. Designed around a specific investment thesis:

> A stock that's already been #1 for a year has no upside left — it's
> "expensive" by the time we see it. A stock climbing from rank 80 → 40 → 5 is
> more interesting because we're catching it before everyone else does.
> Decliners should be punished hard — that's an exit signal.

So momentum is the *dominant* signal here, with current rank quality as a
secondary check ("is this stock even in the game?").

#### Algorithm

Given the last **N = 5** months of a stock's ranks (newest first, with `101`
filled in for any month it wasn't in the top 100):

**Step 1 — convert ranks to values**

```
values[i] = max(0, 101 - ranks[i])      # rank 1 → 100, rank 101 → 0
```

**Step 2 — base score** (recency-weighted average of values, 0..100)

```
pos_decay = [1.0, 0.8, 0.6, 0.4, 0.2]   # (N - i) / N
base = sum(values[i] * pos_decay[i]) / sum(pos_decay)
```

This answers *"how good are the recent ranks?"* without caring about
direction. Same decay shape as `sa/score_decayed`, just normalised by the sum
of the weights so the result is on a clean 0..100 scale.

**Step 3 — slopes between consecutive months** (positive = improving)

```
slopes[i] = values[i] - values[i + 1]   # 4 slopes for N = 5
```

A stock that went `[1, 4, 9, 101, 101]` has slopes `[3, 5, 92, 0]` — the
big number is the month it first appeared in the rankings.

**Step 4 — momentum** (recency-weighted average of slopes, −100..+100)

```
slope_decay = [1.0, 0.75, 0.5, 0.25]    # (N - 1 - i) / (N - 1)
momentum = sum(slopes[i] * slope_decay[i]) / sum(slope_decay)
```

The most recent slope counts most. *Both* recency weightings — on ranks
**and** on slopes — are needed:
- decay on ranks tells us "how good is the stock NOW vs. five months ago"
- decay on slopes tells us "did the move happen NOW vs. five months ago"

Dropping either one would collapse different stocks onto the same score.

**Step 5 — final score**

```
MOMENTUM_WEIGHT = 2.0
final = base + MOMENTUM_WEIGHT * momentum
```

A `MOMENTUM_WEIGHT` of 2.0 is what makes improvers beat the "stable #1"
anchor. With a smaller weight, no amount of climbing could ever beat the
boring 100/100 stable top — which is exactly the wrong outcome for this view.

#### Reading the score

The mental anchor is **100 = stable rank 1 every month** ("no upside left").

| Score | Interpretation |
| --- | --- |
| **> 110** | Rising star — recently climbing or just entered the top |
| **~ 100** | Stable top performer (no momentum, but no decline either) |
| **50 – 100** | Decent stock, neither rising nor falling fast |
| **0 – 50** | Mid-pack, possibly drifting |
| **< 0** | Active decliner — exit signal |

#### Worked examples

| Ranks (newest → oldest) | base | momentum | **final** | what's going on |
| --- | ---: | ---: | ---: | --- |
| `[1, 1, 1, 101, 101]` |  80.0 |  20.0 | **120.0** | New stock that parked at #1 for 3 months |
| `[1, 4, 9, 101, 101]` |  77.6 |  21.1 | **119.8** | Sharp climber, just hit #1 |
| `[1, 101, 101, 101, 101]` |  33.3 |  40.0 | **113.3** | Just appeared at #1 — big momentum bonus |
| `[1, 20, 40, 60, 80]` |  74.0 |  19.6 | **113.2** | Long climb 80 → 1 |
| `[6, 19, 20, 101, 101]` |  69.7 |  21.7 | **113.1** | Steady improver |
| `[5, 40, 75, 101, 101]` |  53.5 |  29.7 | **112.9** | Big improver 75 → 5 |
| `[5, 5, 5, 5, 101]` |  89.6 |   9.6 | **108.8** | Stable at #5 with 4 months of history |
| `[12, 7, 8, 101, 101]` |  73.3 |  16.9 | **107.1** | Was rising, slipped recently — lower than steady improver |
| `[1, 1, 1, 1, 1]` | 100.0 |   0.0 | **100.0** | **The anchor**. Stable #1 = "no upside" |
| `[20, 30, 40, 50, 60]` |  67.7 |  10.0 | **87.7** | Mid-pack slow climber |
| `[60, 50, 40, 30, 20]` |  54.3 | -10.0 | **34.3** | Mid-pack slow decliner — same ranks reversed, ~50 point spread |
| `[50, 50, 50, 50, 50]` |  51.0 |   0.0 | **51.0** | Stable mid-pack baseline |
| `[90, 90, 90, 90, 90]` |  11.0 |   0.0 | **11.0** | Stable bottom of the list |
| `[80, 60, 40, 20, 1]` |  47.6 | -19.9 | **7.8**  | Long decline from #1 down to 80 — almost out |
| `[101, 5, 5, 5, 5]` |  64.0 | -38.4 | **-12.8** | Was stable #5, just dropped out — exit |
| `[101, 1, 1, 1, 1]` |  66.7 | -40.0 | **-13.3** | Was stable #1, just dropped out — exit |
| `[101, 101, 1, 1, 1]` |  40.0 | -30.0 | **-20.0** | Was #1 for 3 months, gone for 2 |

A few things worth noting from the table:

- **Roller coasters self-cancel.** Slopes telescope, so a stock that bounces
  5 → 101 → 5 → 101 → 5 has slopes that mostly add to zero. Volatility gets
  punished without an explicit volatility term.
- **The same ranks in reverse direction get very different scores.** Compare
  `[20, 30, 40, 50, 60]` (87.7, climbing) vs. `[60, 50, 40, 30, 20]` (34.3,
  falling) — a ~50 point spread on identical raw numbers.
- **Recent slips matter.** `[12, 7, 8, 101, 101]` scores below
  `[6, 19, 20, 101, 101]` even though ranks 7-8 are inherently better than
  19-20, because the slip from 7 → 12 is the most recent move and counts most.

#### Tuning knobs

These live as class constants on `CompiledSAScoreMomentum` so they can be
tweaked without a migration:

- `WINDOW_MONTHS = 5` — how far back to look
- `MOMENTUM_WEIGHT = 2.0` — how much momentum dominates over current rank
  - `0.6` → stable #1 is unbeatable (wrong for this view)
  - `1.0` → improvers tie stable #1
  - `2.0` → improvers score ~113-120, stable #1 = 100 (current default)

---

## Cron endpoints

Each compiled-score view is populated by a cron-triggered endpoint that scans
for ratings dumps newer than the latest compilation and updates accordingly:

| Endpoint | Compiles |
| --- | --- |
| `cron/compile_sa_score/` | `sa/score` |
| `cron/compile_sa_score_decayed/` | `sa/score_decayed` |
| `cron/compile_sa_score_momentum/` | `sa/score_momentum` |

Each accepts an optional `?limit=N` query string to cap the number of rating
types processed per run (default 5, so a single cron invocation doesn't try to
recompute all 14 categories at once).