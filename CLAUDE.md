# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Home Hub is a single-file Tkinter desktop start page for Linux. It shows a clock, weather from Open-Meteo, one headline per news topic from Google News RSS, recent folders and pinned app launchers. No API keys are needed. Python 3.10+.

## Commands

```bash
./install-dependencies.sh                 # pip install -r requirements.txt (requests, Pillow), then checks for Tkinter
python3 hub.py                            # launch the GUI
python3 hub.py --check                    # headless: fetch weather + news, print a report (hits the network)
python3 -m unittest discover -s tests -v  # full test suite (offline, no display needed)
python3 -m unittest tests.test_hub.NewsTests.test_parse_news_sorted_newest_first   # single test
./install.sh / ./uninstall.sh             # add/remove ~/.local/share/applications and ~/.config/autostart .desktop entries
```

There is no linter, formatter or build step configured.

The tests import `hub`, which runs `import tkinter` at module level. So the tests need a Python that has Tkinter installed (`python3-tkinter` on Fedora, `python3-tk` on Debian), even though they never open a window. Without it, every test fails with an `ImportError`. Tkinter comes from the OS package manager, not pip.

## Architecture

Everything lives in `hub.py`, with section banners in this order: theme, app table and defaults, config/cache I/O, recent folders, news, weather, launching, widgets, `HubApp`, entry points. `tests/test_hub.py` tests only the pure functions. Network calls are mocked by patching `hub.http_get`, `hub.resolve_location`, `hub.geocode` or `hub.detect_ip_location`.

**Optional dependencies.** `requests` and `PIL` are imported in try/except blocks and set to `None` if missing. `http_get` falls back to `urllib`. Icon loading is skipped if PIL is missing, and tiles show the app's `monogram` instead. Keep these guards when you touch either library.

**Theming uses mutable module globals.** `apply_theme(name)` calls `globals().update(palette)`, which rebinds `BASE`, `TEXT`, `BLUE` and the other colour names, and rebuilds `TOPIC_COLORS`. So:
- Code must read colour globals at call time. Default arguments such as `bg: str = BASE` are fixed to Mocha when the module is imported, so pass colours explicitly whenever the theme matters.
- `APPS[...]["color"]` stores a palette *name* (for example `"GREEN"`), which `resolve_color()` turns into a hex value for the current theme.
- Changing the theme or other settings calls `HubApp._rebuild_ui()`, which destroys every widget, re-normalizes the config, applies the theme and rebuilds the UI from scratch. Widgets are not restyled in place.

**Config and cache.**
- `config.json` and `cache.json` sit next to `hub.py`, found through `APP_DIR`.
- `load_config()` always runs `normalize_config()`. That function deep-merges onto `DEFAULT_CONFIG`, then dedupes and limits topics to `MAX_TOPICS` (8), clamps the weather options, and drops pins that don't match an app in the registry. Any new config key needs a default in `DEFAULT_CONFIG` and validation in `normalize_config()`.
- Both files are tracked in git, and running the app or `--check` rewrites them. Don't commit those changes by accident.

**App registry.** `build_app_registry(cfg)` combines the built-in `APPS` table with `cfg["custom_apps"]`, which `normalize_custom_apps()` cleans up and gives keys like `custom-<slug>`. `build_launch_command()` wraps apps marked `terminal: True` in the first terminal it finds (`hold` keeps the terminal open after the command exits). `launch_app()` starts the process.

**Refresh pipeline (threads → queue → Tk main loop).**
- `refresh_all()` increments `self.generation`, takes a deep copy of the config, and starts one daemon thread for weather and one per news topic.
- Each worker puts a `(kind, generation, ...)` tuple on `self.queue`. Workers never touch Tk widgets.
- `_poll_queue()` runs every 250 ms on the Tk thread. It discards messages from older generations, applies the rest, and calls `_finish_refresh()` once `pending` reaches 0.
- When a fetch succeeds, its result is written to `cache.json`. When it fails, the cached data is shown marked as stale, and the status bar says "offline".
- `_schedule_periodic_refresh()` re-runs the refresh every `weather.refresh_minutes`.

**The 24-hour news rule.** `fetch_news_article()` queries Google News with `when:1d`. `parse_news()` then checks each `pubDate` again: articles older than `NEWS_WINDOW_HOURS`, or more than 2 hours in the future, are dropped. If nothing is left, the card says so instead of showing an older story.

**Weather.** `get_weather()` calls `resolve_location()` to find the location. In `auto` mode it uses the IP address (and reuses the location stored in the cache). In `manual` mode it geocodes `location.city` through Open-Meteo. It then fetches the forecast and returns a flat dict that `HubApp.render_weather()` draws on a canvas.

**Recent folders.** `recent_folders()` combines folders opened through the hub (`cache["recent_folders"]`, added by `record_recent_folder`) with folder entries from GTK's `~/.local/share/recently-used.xbel`.

## Notes

- `APPS` contains machine-specific launchers: Flatpak Spotify and VS Code, `~/.local/bin/hermes`, `opencode` and `ollama`. Edit it there when changing the defaults.
- According to the README, the app was written entirely by an AI agent (DeepSeek) as a learning project.
