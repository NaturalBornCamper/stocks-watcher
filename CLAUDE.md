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

Whenever you add, rename, or change a Run configuration (new management command, new test module, etc.), update **both** files in the same change. The PyCharm `folderName` attribute corresponds to the VS Code `presentation.group` (`CRON` ↔ `2-CRON`, `Tests` ↔ `3-Tests`). Order numbers in `presentation.order` should be unique within a group.

If a new test module is added, also update the "Run ALL Tests" entry in both files so the umbrella runner includes it.

## Development Commands

```bash
# Run development server
python manage.py runserver

# Database migrations
python manage.py makemigrations
python manage.py migrate

# Run all tests
python manage.py test

# Run a single test module
python manage.py test library.tests.test_steam_cache_service

# Data management commands (all support --limit N, --game-id ID)
python manage.py refresh_steam_api_cache [--dry-run]
python manage.py refresh_steam_headers [--dry-run]
python manage.py refresh_igdb_api_cache [--dry-run]
python manage.py fill_steam_ids_from_igdb_ids [--dry-run]
python manage.py fill_igdb_ids_from_steam_ids [--dry-run]
python manage.py fetch_completion_times
python manage.py fetch_release_dates
python manage.py refresh_app_cards_block
python manage.py list_games
```

Set `DJANGO_SETTINGS_MODULE=settings.dev` for local work. Copy `.env.example` to `.env` and fill in IGDB credentials.

## Architecture

This is a Django 5.2 app — a personal video game library manager that pulls data from Steam and IGDB APIs and renders it in a web UI.

### Data Layer

**Models** (`library/models/`): `Game` is the core record. `Platform`, `Tag`, and `TagGroup` describe how the game is categorized. `GamePlatform` and `GameTag` are the join tables. `GameApiFetchState` tracks cooldown state per game so API requests are not repeated too soon. `AdditionalSteamId` handles games with multiple Steam app IDs.

**Game data on disk** (`game_data/`): API responses are cached as JSON files, not in the database. Layout:
- `steam/api_data/` — Steam Store API JSON responses
- `steam/headers/`, `steam/screenshots/` — downloaded images
- `igdb/` — IGDB data and cover art (resized to banner dimensions)
- `custom_steam/` — manual override JSONs used when no API cache exists
- `defaults/` — last-resort fallback JSON for games with no data at all

### Provider / Service / View Pipeline

1. **Providers** (`library/providers/`) make the actual HTTP calls. `SteamStore` hits the Steam Store API. `IGDBProvider` calls IGDB (games, external_games, time_to_beat). `HowLongToBeatProvider` scrapes HLTB. All share `AbstractBaseProvider`.

2. **Cache services** (`library/services/`) manage reading and writing the on-disk JSON. `SteamCacheService` and `IGDBCacheService` both extend `BaseGameCacheService`. The fallback hierarchy is: fresh cache → stale cache (if refresh fails) → custom override JSON → default JSON.

3. **Header image services** (`steam_header.py`, `igdb_header.py`) own the header-banner downloads. Workflow is intentionally asymmetric between providers because the providers are: Steam header URLs are derivable from `steam_id` alone (no API call needed), so Steam has its own `refresh_steam_headers` cron and a per-game cooldown stored in `GameApiFetchState`. IGDB cover URLs contain an opaque hash that only appears in the IGDB API response, so the IGDB header download stays bundled with `refresh_igdb_api_cache` (called from `IGDBCacheService.postprocess_refresh_success`) — no separate IGDB header cron exists.

4. **Views** (`library/views/`):
   - `index()` — renders the library grid using pre-built cached HTML card blocks; rebuilt on demand by `refresh_app_cards_block`.
   - `tab()` — serves an HTML fragment for a single game, loaded via AJAX. The Steam tab cache is considered stale after `TAB_STEAM_CACHE_MAX_AGE_HOURS` (12 h).
   - `media_asset()` — serves provider-scoped images with path validation to block directory traversal.

5. **`game_tab.build_render_data()`** (`library/services/game_tab.py`) is the orchestration point for the tab view. It decides whether to show Steam or IGDB data and assembles all fields needed for the template.

### Cache Invalidation

Django signals in `library/signals.py` automatically invalidate the cached game-cards HTML block whenever a `Game`, `Platform`, or `Tag` record is saved or deleted, so the index page stays consistent without manual cache-busting.

### Price Label Logic

Price display is derived from Steam's `price_overview` and `is_free` fields, not stored directly. A game delisted from Steam gets a top-level `delisted: true` flag in its cached JSON (and the `price_overview` block is dropped). This is set automatically when Steam returns `{"success": false}` for the app, and can also be set by hand in `game_data/custom_steam/api_data/` for permanently delisted games. The same convention applies to IGDB cache files when IGDB returns "not found".

### Settings

- `settings/base.py` — shared config, IGDB credentials, cache settings, feature flags
- `settings/dev.py` — SQLite3, logs queries to `django_queries.log`
- `settings/production.py` — SQLite3, sets `STATIC_ROOT`

Key constants (in `base.py`): `TAB_STEAM_CACHE_MAX_AGE_HOURS`, `INDEX_PAGE_LOAD_API_REQUEST_BUDGET`, `DEFAULT_GAME_NOT_FOUND_API_COOLDOWN_HOURS`, `STEAM_HEADER_IMAGE_URL_TEMPLATES` (CDN mirrors for header art), `STEAM_HEADER_REDOWNLOAD_AFTER_HOURS`.

`Game.hidden=True` is the catch-all "ignore this game" flag: hidden games are excluded from every cronjob's queryset (Steam/IGDB API caches, header downloads, ID resolution, completion times, release dates) and from the index grid and tab view. The flag stays editable in admin so you can keep records of crappy/duplicate/beta games without polluting the rest of the app.

Steam header images are downloaded by the `refresh_steam_headers` cron straight from the Steam CDN (`shared.fastly.steamstatic.com` with `shared.akamai.steamstatic.com` as a backup mirror). No Steam API call is needed; the URL is built from `steam_id`. Per-game cooldowns live in `GameApiFetchState` under the `download_steam_header_image` operation: long after a successful download, short after a failure.

### Testing

Tests live in `library/tests/`. The test suite uses Django's `TestCase` with `LocMemCache` and fixture JSON files that mock API responses. `test_provider_live_smoke.py` hits real APIs and should not be run in CI.