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

Whenever you add, rename, or change a Run configuration (new management command, new test module, etc.), update **both** files in the same change.

Multi-step configurations are chained, never wrapped in a management command. PyCharm chains with "before launch" `RunConfigurationTask` entries (see `Monthly_SA_Dumps_Aggregate_Edgar_IDs_Backport.xml`); VS Code mirrors the same chain with a `dependsOrder: "sequence"` task in `.vscode/tasks.json`, wired to the launch entry via `preLaunchTask`. When a chain changes, all three places (PyCharm XML, `tasks.json`, `launch.json`) must stay in sync. The PyCharm `folderName` attribute corresponds to the VS Code `presentation.group` (`Migration` ↔ `1-Migration`, `Commands` ↔ `2-Commands`, `Score Compilation` ↔ `3-Score Compilation`, `Price Watcher` ↔ `4-Price Watcher`; future `Tests` would map to `5-Tests`). Order numbers in `presentation.order` should be unique within a group.

Secrets / API keys do **not** belong in these files. Both PyCharm and VS Code load `.env` (gitignored) — PyCharm via `<option name="ENV_FILES" value="$PROJECT_DIR$/.env" />`, VS Code via `"envFile": "${workspaceFolder}/.env"`. Only `PYTHONUNBUFFERED` and `DJANGO_SETTINGS_MODULE` should stay in the run-config env (they are tied to run mode, not to the machine).

When tests eventually exist (none yet), follow the Games Library pattern: one config per test module under a `Tests` / `5-Tests` group, plus an umbrella "Run ALL Tests" entry that must be updated whenever a new test module is added.

## Development Commands

```bash
# Run development server (PyCharm/VS Code config: "Run Dev Server")
python manage.py runserver

# Database migrations ("Make Migrations" / "Migrate" run configs)
python manage.py makemigrations
python manage.py migrate

# The standard monthly operation is the run configuration
# "Monthly SA Dumps (Aggregate + Edgar IDs + Backport)": aggregate the fresh
# per-category exports into the monthly CSV, stamp the new file's Edgar ids,
# then backport current symbols to the older CSVs. No wrapper command on
# purpose (keeps the codebase light): the config chains three commands --
# sa_ratings_manipulations one_csv_per_date -> fetch_edgar_ids ->
# rename_old_symbols (see "Run Configurations" above).

# Import a month's SA ratings dump CSV(s) ("Import SA Ratings")
python manage.py import_sa_ratings "data_dumps/seeking_alpha/*.csv"

# Reorganise raw SA dump CSVs into one CSV per date ("Generate Monthly SA Dump")
python manage.py sa_ratings_manipulations one_csv_per_date \
    "data_dumps/seeking_alpha/" "data_dumps/seeking_alpha/"

# Monthly dump maintenance, run AFTER the reorganise step above ("Fetch Edgar
# IDs" then "Rename Old Symbols"): stamp each row's permanent SEC id (CIK),
# then rewrite old dumps so a company that changed ticker keeps one symbol
# (same CIK = same company; share classes like GOOG/GOOGL are kept apart).
# Review the git diff, commit.
python manage.py fetch_edgar_ids ["data_dumps/seeking_alpha/2025-05-01.csv"]  # default = newest monthly dump
python manage.py rename_old_symbols
# (The one-time 2026-06 bulk cleanup tooling -- find_symbol_changes, clean_dumps
# and the curated _symbol_renames.csv -- was deleted afterwards; recover from
# git history if a no-CIK stock ever needs a manual retroactive rename.)

# Compile per-stock scores after a new ratings dump. Each command skips rating
# types already up to date for the latest dump. Run on a schedule via the cron
# runner (resources/run-cronjob.sh) -- see "Cron jobs" below. Run configs:
# "Compile SA Score" / "Compile SA Score Decayed" / "Compile SA Score Momentum".
python manage.py compile_sa_score                              # all-time cumulative
python manage.py compile_sa_score_decayed                      # recent-months decay
python manage.py compile_sa_score_momentum                     # momentum / rising stars
# Optional tuning flags (defaults come from the compiled-model constants):
#   --limit N  --decay-months N  --decay-base F  --window-months N  --momentum-weight F

# Price-watcher crons. Run on a schedule via the cron runner -- see "Cron jobs".
# Run configs: "Fetch Prices" / "Send Alerts".
python manage.py fetch_prices                                  # download due stocks' latest prices (--limit N)
python manage.py send_alerts                                   # email any price alerts that fired

# Research backtest comparing scoring algorithms (NOT a routine user command --
# Claude runs this when investigating algorithm tweaks; output -> quant_simulations/)
python manage.py backtest_scores

# Dev / data maintenance (destructive -- truncates tables)
python manage.py db_operations empty_sa_stocks
python manage.py db_operations empty_sa_ratings
python manage.py db_operations empty_compiled_scores
python manage.py db_operations empty_compiled_scores_decayed
python manage.py db_operations empty_compiled_scores_momentum
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
- Ticker identity lives in `apps/quant/symbols/`: `edgar.py` downloads/caches the SEC ticker→CIK mapping (a CIK is a permanent company id that survives ticker/name changes; stored on `SAStock.external_id` and stamped as a `CIK` column in the dump CSVs by `fetch_edgar_ids`), `matching.py` knows share-class pairs (GOOG/GOOGL) so they are never merged, `dumps.py` reads/writes the dump CSVs. `rename_old_symbols` rewrites old dumps to today's tickers, using the newest monthly dump as the truth. At import, an unknown ticker whose CIK matches exactly one known stock renames that stock in place so its history stays attached; otherwise the stock is created as new. Stocks without a CIK match by ticker only (admin filter "has Edgar id: No" lists them for manual digging). The Quant DB stays disposable — the CSVs are the source of truth.
- Score compiling lives in the `compile_sa_score*` management commands (`apps/quant/management/commands/`), triggered on a schedule by the cron runner. Each command skips rating types already up to date for the latest dump. Shared date/query helpers are in `apps/quant/scoring.py`. The old `/quant/cron/compile_sa_score_*/` URLs still work as thin wrappers (`apps/quant/views/cron.py`) that forward query params to the matching command and return its output as text.
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

### Cron jobs

Scheduled jobs run as management commands, not browser URLs. The generic runner
`resources/run-cronjob.sh` is deployed to the server and called like:

```bash
$HOME/tools/run-cronjob.sh stocks-watcher compile_sa_score_decayed --limit=5
```

It runs `manage.py <command> [args...]`, auto-adds `--settings=settings.production`,
and writes a rotating per-job log to `<app>/logs/<command>.log` (stdout + stderr).
Because the runner captures stdout, commands should write progress with
`self.stdout.write(...)` / `self.style.SUCCESS(...)`, not bare `print`.

All five crons are migrated to commands: quant scores (`compile_sa_score`,
`compile_sa_score_decayed`, `compile_sa_score_momentum`) and watcher
(`fetch_prices`, `send_alerts`). Their old `/cron/...` URLs still work as thin
wrappers (`apps/*/views/cron.py`) that forward query params to the command.
Shared bits live next to each app: `apps/quant/scoring.py` and
`apps/watcher/notifications.py` (the `send_email` helper).

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
