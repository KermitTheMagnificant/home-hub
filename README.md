### DISCLAIMER
This app was made entirely with AI, specifically DeepSeek 4.1 Flash. The purpose of this was for me to learn more about how AI agents work, how to use them, etc... 
So, keep that it mind, as it may have certain unwanted "features" of AI. This also means I may not update it that often. 

# Home Hub

A local desktop start page: a live clock, customisable weather and forecast, one
news headline per topic you choose, recently opened folders, and pinned shortcuts
for built-in apps or any application on your computer.

Built with Python and Tkinter. Weather comes from Open-Meteo and headlines from
Google News RSS, so no API keys are required.

## Quick start

```bash
cd ~/home-hub
python3 hub.py
```

To check the data sources without opening a window (useful on a headless machine):

```bash
python3 hub.py --check
```

## Features

- Live local clock, date and time-of-day greeting.
- Current conditions, feels-like, humidity, wind, high/low, sunrise/sunset,
  a 12-hour temperature chart and a configurable daily forecast.
- Weather location can be auto-detected from your IP address, or fixed to a city.
- Weather display is configurable: show or hide the hourly chart, daily forecast,
  sunrise/sunset and detail stats; choose 1-7 forecast days and a 5-120 minute
  refresh interval.
- One to eight independent news topics. Each card shows the newest article
  published in the last 24 hours, with source and age; click a card to open it.
  The article list is scrollable and lives on the left side of the window.
- A **Recent folders** section on the left lists folders from your desktop's
  recent-file history plus folders opened through the hub. Use **Browse...** to
  open any folder and add it to the list.
- Pinned app shortcuts. Click a tile to launch, right-click to unpin, or use
  **Edit pins** to choose which apps appear. Add custom shortcuts for any
  application by name and command in Settings.
- Five visual themes: Catppuccin Mocha, Macchiato, Frappe, Latte and Nord.
- Cached weather and headlines are shown while offline.
- Refreshes on your chosen interval; cached data is displayed immediately at startup.

## Controls

| Action | Shortcut |
| --- | --- |
| Toggle fullscreen | `F11` |
| Leave fullscreen | `Esc` |
| Refresh weather and news | `Ctrl+R` |
| Open settings | `Ctrl+,` |
| Open an article | Click its card |
| Open a recent folder | Click its row |
| Add a folder | **Browse...** in Recent folders |
| Unpin an app | Right-click its tile |
| Manage pins | **Edit pins** in the Shortcuts panel |

Settings lets you change the theme, city, units, weather display options, news
topics, pinned apps and custom application shortcuts.

## Configure

Settings are stored in `config.json` next to `hub.py`. You can edit it directly:

```json
{
  "location": {
    "mode": "auto",
    "city": "",
    "latitude": null,
    "longitude": null,
    "label": ""
  },
  "units": "metric",
  "theme": "mocha",
  "topics": ["Technology", "Science", "Business", "Sports", "Health"],
  "pinned": ["spotify", "opencode", "ollama", "hermes", "vscode", "github"],
  "custom_apps": [
    {
      "key": "custom-firefox",
      "name": "Firefox",
      "launch": ["firefox", "--new-window"],
      "icon": "firefox",
      "terminal": false
    }
  ],
  "weather": {
    "forecast_days": 5,
    "show_hourly": true,
    "show_forecast": true,
    "show_sun": true,
    "show_details": true,
    "refresh_minutes": 15
  }
}
```

- `location.mode`: `auto` (IP-based) or `manual` (uses `city`).
- `units`: `metric` (Celsius, km/h) or `imperial` (Fahrenheit, mph).
- `theme`: `mocha`, `macchiato`, `frappe`, `latte` or `nord`.
- `topics`: one to eight different strings, e.g. `"AI"`, `"Climate"`, `"Finance"`,
  `"Football"`, `"Space"`.
- `pinned`: any subset of the built-in apps plus custom shortcut keys.
- `custom_apps`: shortcuts for any installed application. `launch` may be a list
  or a command string; add one through Settings to have it pinned automatically.
- `weather.forecast_days`: 1-7. `weather.refresh_minutes`: 5-120. The
  `show_*` flags control which parts of the weather card are drawn.

Built-in launcher commands live in the `APPS` table near the top of `hub.py` if you
need to adjust a path for your system. By default the hub uses the Flatpak installs
of Spotify and VS Code, the local `hermes`, `opencode` and `ollama` binaries, and
opens GitHub in the browser. CLI apps (`OpenCode`, `Ollama`) open in a terminal.

## Autostart

Run the installer to add a menu entry and start Home Hub automatically after login:

```bash
./install.sh
```

Remove the menu entry and autostart hook with:

```bash
./uninstall.sh
```

The installer does not launch the app or change any other settings. It only writes
`~/.local/share/applications/home-hub.desktop` and
`~/.config/autostart/home-hub.desktop`.

## Requirements

- Python 3.10+
- Tkinter (`python3-tk` on Fedora/Debian)
- `requests` (already present in most environments)
- Pillow (optional; used to render real app icons)

```bash
python3 -m pip install -r requirements.txt
```

If Pillow is missing, shortcuts fall back to colored monograms.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests cover RSS parsing and the 24-hour filter, relative time formatting,
config normalization, themes, custom shortcuts, recent folders, weather parsing
and the launcher table. They do not require a display or network access.

## How the 24-hour rule works

Google News is queried with `when:1d` for each topic, then every `pubDate` is
checked again against the current time. Articles older than 24 hours (or more than
two hours in the future, allowing for clock skew) are discarded. If a topic has no
qualifying article, its card says so instead of showing an older story.

## Files

```
hub.py              application
config.json         user settings
cache.json          last successful weather/news (created at runtime)
assets/home-hub.png launcher/window icon
install.sh          install menu entry + autostart
uninstall.sh        remove them
tests/              offline unit tests
```
