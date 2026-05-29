# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Code Style

- Prefer plain English over backend jargon. Avoid words like `persist`, `orchestrate`, `hydrate`, `serialize`, and `normalize` unless they are clearly the standard term and simpler wording would be misleading.
- Prefer names like `save_*`, `record_*`, `load_*`, `update_*`, `build_*`, `fetch_*`, and `find_*`.
- Write docstrings in simple English. Explain what the method is for in practical terms.
- Keep method and variable names easy to understand for someone who is not a native English speaker.

## Readability

- Add short comments above non-obvious code blocks inside methods. Use comments to explain intent, not obvious mechanics.
- If a helper is used only once, inline it unless extracting it clearly makes the code easier to read.
- Avoid one-line helpers unless they represent a clear shared concept used in multiple places. Keep the logic inline with a short comment instead.
- Prefer smaller, direct methods over abstract helper layers when that improves readability.

## Run Configurations

Run configurations live in **two parallel files** that must always be kept in sync:

- PyCharm: `.idea/runConfigurations/<Name>.xml` (one file per entry)
- VS Code: `.vscode/launch.json` (single file with one entry per configuration)

Whenever you add, rename, or change a Run configuration (new management command, new test module, etc.), update **both** files in the same change. The PyCharm `folderName` attribute corresponds to the VS Code `presentation.group` (`Migration` ↔ `1-Migration`, `Commands` ↔ `2-Commands`; future `Tests` would map to `3-Tests`). Order numbers in `presentation.order` should be unique within a group.

Secrets / API keys do **not** belong in these files. Both PyCharm and VS Code load `.env` (gitignored) — PyCharm via `<option name="ENV_FILES" value="$PROJECT_DIR$/.env" />`, VS Code via `"envFile": "${workspaceFolder}/.env"`. Only `PYTHONUNBUFFERED` and `DJANGO_SETTINGS_MODULE` should stay in the run-config env (they are tied to run mode, not to the machine).

When tests eventually exist (none yet), follow the Games Library pattern: one config per test module under a `Tests` / `3-Tests` group, plus an umbrella "Run ALL Tests" entry that must be updated whenever a new test module is added.

## Development Commands

```bash
# Run development server (PyCharm/VS Code config: "Run Dev Server")
python manage.py runserver

# Database migrations ("Make Migrations" / "Migrate" run configs)
python manage.py makemigrations
python manage.py migrate

# Standard monthly SA refresh: reorganise raw dumps + import ("Refresh SA Ratings")
# Wraps the two commands below; stops if the reorganise step fails.
python manage.py refresh_sa_ratings

# Import a month's SA ratings dump CSV(s) ("Import SA Ratings")
python manage.py import_sa_ratings "data_dumps/seeking_alpha/*.csv"

# Reorganise raw SA dump CSVs into one CSV per date ("Generate Monthly SA Dump")
python manage.py sa_ratings_manipulations one_csv_per_date \
    "data_dumps/seeking_alpha/" "data_dumps/seeking_alpha/"

# Research backtest comparing scoring algorithms (NOT a routine user command --
# Claude runs this when investigating algorithm tweaks; output -> quant_simulations/)
python manage.py backtest_scores

# Dev / data maintenance (destructive -- truncates tables)
python manage.py db_operations empty_sa_stocks
python manage.py db_operations empty_sa_ratings
python manage.py db_operations empty_compiled_scores
python manage.py db_operations empty_compiled_scores_decayed
python manage.py db_operations empty_all_quant
```

Copy `.env.example` to `.env` and fill in the email / price-API credentials. `DJANGO_SETTINGS_MODULE=settings.dev` is set in the run-config env (not in `.env`) because it is tied to the run mode, not to the machine.

## Architecture

A Django app that ingests monthly Seeking Alpha "top 100" stock ratings, compiles per-stock scores from the rank history under several scoring algorithms, and renders a dark-themed web grid comparing stocks across SA categories.

URL prefixes (project `urls.py`):
- `""` (root) → `apps.watcher`
- `/quant/` → `apps.quant`
- `/admin/` → Django admin

### Apps

**`apps/quant/`** — Seeking Alpha ratings, scoring algorithms, and the main frontend grids.
- Models: `SAStock`, `SARating`, `CompiledSAScore`, `CompiledSAScoreDecayed`, `CompiledSAScoreMomentum`.
- Cron endpoints under `/quant/cron/compile_sa_score_*/` recompile per-stock scores when a new ratings dump is detected. Each endpoint skips rating types already up to date for the latest dump.
- Frontend views (`apps/quant/views/score.py`):
  - `/quant/sa/score` — all-time cumulative score
  - `/quant/sa/score_decayed` — recent-months exponential decay
  - `/quant/sa/score_momentum` — momentum / rising-stars
  - `/quant/sa/count` — # of months each stock has been ranked
  - `/quant/sa/month[/<YYYY-MM>]` — single-month rank view with date selector

**`apps/watcher/`** — stock-price tracking, separate from quant.
- Models: `Stock`, `Price`, `Alert`.
- Provider classes for several price APIs in `apps/watcher/providers/` (EODHD, Alpha Vantage, IEX, Marketstack, mboum, RapidAPI). All share `AbstractBaseProvider`.

### Scoring algorithms

The four `Compiled*` models each store per-`(sa_stock, type)` rows of `{score, count, latest_sa_ratings_date}`. They differ only in how `score` is computed:

| Model | Idea | Cron |
| --- | --- | --- |
| `CompiledSAScore` | All-time `sum(101 - rank)` over every month, no decay | `cron/compile_sa_score/` |
| `CompiledSAScoreDecayed` | Last N months, exponential `DECAY_BASE^i` weight (default N=3, base=0.5 → `[1.0, 0.5, 0.25]`) | `cron/compile_sa_score_decayed/` |
| `CompiledSAScoreMomentum` | Base + 2 × momentum (slopes between consecutive months) — designed to catch rising stars | `cron/compile_sa_score_momentum/` |

Tuning knobs (e.g. `DECAY_BASE`, `WINDOW_MONTHS`, `MOMENTUM_WEIGHT`) live as class constants on each compiled model, so the cron formula can be tweaked without a migration. Per-request overrides are accepted (`?decay_base=0.7` etc.) for experimentation.

### Frontend

- All templates extend `apps/quant/templates/base.html`.
- Global stylesheet at `static/css/style.css` (single dark theme — admin is intentionally not affected; it uses its own templates).
- Table sort JS at `static/js/table-sort.js`, loaded globally from `base.html`. Looks for `<table class="sortable">` and wires click-to-sort with ▲ / ▼ indicators on the active header. Pre-extracts values once per sort and applies the new order via a single `DocumentFragment` append.
- SA-ratings nav: template partial `_sa_ratings_menu.html`, included from `seeking_alpha.html`. Each link has a `title` tooltip explaining what its score does.
- Gating row colours (red / orange / yellow) on the score/decayed/momentum/count views indicate stocks missing from this month's and/or last month's SA ratings — see `apps/quant/views/score.py:score_or_count` for the rules. They are most informative on the all-time `score` view (corpse risk).

### Simulations / backtests

`apps/quant/management/commands/backtest_scores.py` runs rolling top-7 portfolio simulations across several algorithm variants, fetches Yahoo prices (cached to `quant_simulations/_backtest_price_cache.json`), and writes comparison reports to `quant_simulations/*.txt`.

This is **Claude's research tool**, not part of routine operation. The full handoff doc — what's been tested, what's been dropped, how to re-run, what to revisit when more data exists — is at `quant_simulations/SIMULATIONS_GUIDE.md`. The user-facing 1-pager is `quant_simulations/README.md`.

Long-running decision history (chronological "Follow-up N" entries documenting algorithm experiments) lives in the auto-loaded memory file: `~/.claude/projects/E--DEV-Stocks-Watcher/memory/project_momentum_backtest.md`. Read it first when picking the project back up after a long gap.

### Settings

- `settings/base.py` — shared config, email settings, env-var helpers, `STATICFILES_DIRS`
- `settings/dev.py` — local dev (SQLite `db.sqlite3`, `DEBUG=True`, query log to `django_queries.log`)
- `settings/production.py` — prod (SQLite, sets `STATIC_ROOT`)

Local secrets / API keys live in `.env` (gitignored) and are loaded by run configs via `ENV_FILES` (PyCharm) / `envFile` (VS Code). `.env.example` documents the expected keys.

### Memory directory

In addition to the on-disk docs above, Claude has a per-project memory directory at `~/.claude/projects/E--DEV-Stocks-Watcher/memory/`. The current entries:
- `project_momentum_backtest.md` — chronological history of backtest experiments and algorithm decisions
- `MEMORY.md` — short index of the memory entries
