#!/usr/bin/env python3
"""Home Hub - a desktop start page with a clock, weather, 24-hour news and app shortcuts.

    python3 hub.py            # launch the dashboard
    python3 hub.py --check    # fetch weather + news and print a report (no GUI)

The dashboard uses only Python's standard library plus `requests` and (optionally)
`Pillow` for launcher icons.  Weather data comes from Open-Meteo, headlines from
Google News RSS.  Topics, themes, weather widgets, recent folders and application
shortcuts are all customisable from the settings window.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - urllib fallback is used instead
    requests = None  # type: ignore[assignment]

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - monogram icons are used instead
    Image = None  # type: ignore[assignment]
    ImageTk = None  # type: ignore[assignment]

import tkinter as tk
from tkinter import filedialog
from tkinter import font as tkfont
from tkinter import messagebox


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
CACHE_PATH = APP_DIR / "cache.json"
USER_AGENT = "home-hub/1.0 (personal desktop dashboard)"
NEWS_WINDOW_HOURS = 24

# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "mocha": {
        "BASE": "#1e1e2e", "MANTLE": "#181825", "CRUST": "#11111b",
        "SURFACE0": "#313244", "SURFACE1": "#45475a", "SURFACE2": "#585b70",
        "OVERLAY0": "#6c7086", "OVERLAY1": "#7f849c", "SUBTEXT0": "#a6adc8",
        "SUBTEXT1": "#bac2de", "TEXT": "#cdd6f4", "BLUE": "#89b4fa",
        "LAVENDER": "#b4befe", "MAUVE": "#cba6f7", "PINK": "#f5c2e7",
        "RED": "#f38ba8", "PEACH": "#fab387", "YELLOW": "#f9e2af",
        "GREEN": "#a6e3a1", "TEAL": "#94e2d5", "SKY": "#89dceb",
    },
    "macchiato": {
        "BASE": "#24273a", "MANTLE": "#1e2030", "CRUST": "#181926",
        "SURFACE0": "#363a4f", "SURFACE1": "#494d64", "SURFACE2": "#5b6078",
        "OVERLAY0": "#6e738d", "OVERLAY1": "#8087a2", "SUBTEXT0": "#a5adcb",
        "SUBTEXT1": "#b8c0e0", "TEXT": "#cad3f5", "BLUE": "#8aadf4",
        "LAVENDER": "#b7bdf8", "MAUVE": "#c6a0f6", "PINK": "#f5bde6",
        "RED": "#ed8796", "PEACH": "#f5a97f", "YELLOW": "#eed49f",
        "GREEN": "#a6da95", "TEAL": "#8bd5ca", "SKY": "#91d7e3",
    },
    "frappe": {
        "BASE": "#303446", "MANTLE": "#292c3c", "CRUST": "#232634",
        "SURFACE0": "#414559", "SURFACE1": "#51576d", "SURFACE2": "#626880",
        "OVERLAY0": "#737994", "OVERLAY1": "#838ba7", "SUBTEXT0": "#a5adce",
        "SUBTEXT1": "#b5bfe2", "TEXT": "#c6d0f5", "BLUE": "#8caaee",
        "LAVENDER": "#babbf1", "MAUVE": "#ca9ee6", "PINK": "#f4b8e4",
        "RED": "#e78284", "PEACH": "#ef9f76", "YELLOW": "#e5c890",
        "GREEN": "#a6d189", "TEAL": "#81c8be", "SKY": "#99d1db",
    },
    "latte": {
        "BASE": "#eff1f5", "MANTLE": "#e6e9ef", "CRUST": "#dce0e8",
        "SURFACE0": "#ccd0da", "SURFACE1": "#bcc0cc", "SURFACE2": "#acb0be",
        "OVERLAY0": "#9ca0b0", "OVERLAY1": "#8c8fa1", "SUBTEXT0": "#6c6f85",
        "SUBTEXT1": "#5c5f77", "TEXT": "#4c4f69", "BLUE": "#1e66f5",
        "LAVENDER": "#7287fd", "MAUVE": "#8839ef", "PINK": "#ea76cb",
        "RED": "#d20f39", "PEACH": "#fe640b", "YELLOW": "#df8e1d",
        "GREEN": "#40a02b", "TEAL": "#179299", "SKY": "#04a5e5",
    },
    "nord": {
        "BASE": "#2e3440", "MANTLE": "#292e39", "CRUST": "#242933",
        "SURFACE0": "#3b4252", "SURFACE1": "#434c5e", "SURFACE2": "#4c566a",
        "OVERLAY0": "#616e88", "OVERLAY1": "#7b88a1", "SUBTEXT0": "#a3abbd",
        "SUBTEXT1": "#b8c0d0", "TEXT": "#eceff4", "BLUE": "#88c0d0",
        "LAVENDER": "#b48ead", "MAUVE": "#b48ead", "PINK": "#d08770",
        "RED": "#bf616a", "PEACH": "#d08770", "YELLOW": "#ebcb8b",
        "GREEN": "#a3be8c", "TEAL": "#8fbcbb", "SKY": "#88c0d0",
    },
}

THEME_LABELS = {
    "mocha": "Catppuccin Mocha",
    "macchiato": "Catppuccin Macchiato",
    "frappe": "Catppuccin Frappe",
    "latte": "Catppuccin Latte",
    "nord": "Nord",
}

THEME = "mocha"
BASE = THEMES["mocha"]["BASE"]
MANTLE = THEMES["mocha"]["MANTLE"]
CRUST = THEMES["mocha"]["CRUST"]
SURFACE0 = THEMES["mocha"]["SURFACE0"]
SURFACE1 = THEMES["mocha"]["SURFACE1"]
SURFACE2 = THEMES["mocha"]["SURFACE2"]
OVERLAY0 = THEMES["mocha"]["OVERLAY0"]
OVERLAY1 = THEMES["mocha"]["OVERLAY1"]
SUBTEXT0 = THEMES["mocha"]["SUBTEXT0"]
SUBTEXT1 = THEMES["mocha"]["SUBTEXT1"]
TEXT = THEMES["mocha"]["TEXT"]
BLUE = THEMES["mocha"]["BLUE"]
LAVENDER = THEMES["mocha"]["LAVENDER"]
MAUVE = THEMES["mocha"]["MAUVE"]
PINK = THEMES["mocha"]["PINK"]
RED = THEMES["mocha"]["RED"]
PEACH = THEMES["mocha"]["PEACH"]
YELLOW = THEMES["mocha"]["YELLOW"]
GREEN = THEMES["mocha"]["GREEN"]
TEAL = THEMES["mocha"]["TEAL"]
SKY = THEMES["mocha"]["SKY"]
TOPIC_COLORS: list[str] = []


def apply_theme(name: str) -> str:
    """Load a palette into the module-level colour globals."""
    global THEME, TOPIC_COLORS
    if name not in THEMES:
        name = "mocha"
    palette = THEMES[name]
    globals().update(palette)
    THEME = name
    TOPIC_COLORS = [
        palette["BLUE"], palette["GREEN"], palette["PEACH"], palette["PINK"],
        palette["TEAL"], palette["MAUVE"], palette["YELLOW"], palette["SKY"],
    ]
    return name


apply_theme("mocha")


def resolve_color(value: Any) -> str:
    """Resolve theme colour names (e.g. 'BLUE') to the active palette."""
    if isinstance(value, str) and value in THEMES.get(THEME, {}):
        return str(globals().get(value, value))
    return str(value or TEXT)


DEFAULT_TOPICS = ["Technology", "Science", "Business", "Sports", "Health"]
MAX_TOPICS = 8

APPS: dict[str, dict[str, Any]] = {
    "spotify": {
        "name": "Spotify",
        "icon": "com.spotify.Client",
        "monogram": "S",
        "color": "GREEN",
        "launch": ["flatpak", "run", "com.spotify.Client"],
        "desktop": "com.spotify.Client.desktop",
    },
    "opencode": {
        "name": "OpenCode",
        "icon": None,
        "monogram": "OC",
        "color": "BLUE",
        "launch": ["opencode"],
        "terminal": True,
    },
    "ollama": {
        "name": "Ollama",
        "icon": None,
        "monogram": "OL",
        "color": "MAUVE",
        "launch": ["ollama", "list"],
        "terminal": True,
        "hold": True,
    },
    "hermes": {
        "name": "Hermes",
        "icon": "hermes",
        "monogram": "H",
        "color": "PEACH",
        "launch": [str(Path.home() / ".local" / "bin" / "hermes"), "desktop", "--skip-build"],
        "desktop": "com.nousresearch.hermes.desktop",
    },
    "vscode": {
        "name": "VS Code",
        "icon": "com.visualstudio.code",
        "monogram": "VS",
        "color": "SKY",
        "launch": ["flatpak", "run", "com.visualstudio.code"],
        "desktop": "com.visualstudio.code.desktop",
    },
    "github": {
        "name": "GitHub",
        "icon": None,
        "monogram": "GH",
        "color": "TEXT",
        "launch": ["xdg-open", "https://github.com"],
    },
}

DEFAULT_CONFIG: dict[str, Any] = {
    "location": {
        "mode": "auto",
        "city": "",
        "latitude": None,
        "longitude": None,
        "label": "",
    },
    "units": "metric",
    "theme": "mocha",
    "topics": list(DEFAULT_TOPICS),
    "pinned": list(APPS.keys()),
    "custom_apps": [],
    "weather": {
        "forecast_days": 5,
        "show_hourly": True,
        "show_forecast": True,
        "show_sun": True,
        "show_details": True,
        "refresh_minutes": 15,
    },
}

# Third item is the name of a theme colour, resolved at render time so that
# weather glyphs follow the active theme.
WEATHER_CODE_STYLES: dict[int, tuple[str, str, str]] = {
    0: ("Clear sky", "\u2600", "YELLOW"),
    1: ("Mainly clear", "\u2600", "YELLOW"),
    2: ("Partly cloudy", "\u26c5", "SUBTEXT1"),
    3: ("Overcast", "\u2601", "SUBTEXT1"),
    45: ("Fog", "\u2261", "OVERLAY1"),
    48: ("Rime fog", "\u2261", "OVERLAY1"),
    51: ("Light drizzle", "\u2602", "BLUE"),
    53: ("Drizzle", "\u2602", "BLUE"),
    55: ("Heavy drizzle", "\u2602", "BLUE"),
    56: ("Freezing drizzle", "\u2602", "TEAL"),
    57: ("Freezing drizzle", "\u2602", "TEAL"),
    61: ("Light rain", "\u2602", "BLUE"),
    63: ("Rain", "\u2602", "BLUE"),
    65: ("Heavy rain", "\u2602", "BLUE"),
    66: ("Freezing rain", "\u2602", "TEAL"),
    67: ("Freezing rain", "\u2602", "TEAL"),
    71: ("Light snow", "\u2744", "TEAL"),
    73: ("Snow", "\u2744", "TEAL"),
    75: ("Heavy snow", "\u2744", "TEAL"),
    77: ("Snow grains", "\u2744", "TEAL"),
    80: ("Rain showers", "\u2602", "BLUE"),
    81: ("Rain showers", "\u2602", "BLUE"),
    82: ("Violent showers", "\u2602", "BLUE"),
    85: ("Snow showers", "\u2744", "TEAL"),
    86: ("Snow showers", "\u2744", "TEAL"),
    95: ("Thunderstorm", "\u26a1", "MAUVE"),
    96: ("Thunderstorm", "\u26a1", "MAUVE"),
    99: ("Thunderstorm", "\u26a1", "MAUVE"),
}

UI_FONT = "DejaVu Sans"
MONO_FONT = "DejaVu Sans Mono"


def ui_font(size: int, weight: str = "normal") -> tuple[str, int, str]:
    return (UI_FONT, size, weight)


def mono_font(size: int, weight: str = "normal") -> tuple[str, int, str]:
    return (MONO_FONT, size, weight)


# ---------------------------------------------------------------------------
# Configuration and cache
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "app"


def normalize_custom_apps(raw: Any) -> list[dict[str, Any]]:
    """Validate user-supplied application shortcuts from config.json."""
    apps: list[dict[str, Any]] = []
    taken = set(APPS)
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        command = item.get("launch", item.get("command", []))
        if isinstance(command, str):
            try:
                command = shlex.split(command)
            except ValueError:
                continue
        if not isinstance(command, (list, tuple)):
            continue
        command = [str(part) for part in command if str(part).strip()]
        if not name or not command:
            continue

        key = str(item.get("key") or item.get("id") or "").strip()
        key = re.sub(r"[^A-Za-z0-9_.-]+", "-", key).strip("-") if key else ""
        if not key:
            key = f"custom-{_slugify(name)}"
        if key in taken:
            base = key
            suffix = 2
            while f"{base}-{suffix}" in taken:
                suffix += 1
            key = f"{base}-{suffix}"
        taken.add(key)

        apps.append(
            {
                "key": key,
                "name": name,
                "launch": command,
                "icon": item.get("icon") or None,
                "monogram": str(item.get("monogram") or name[:2].upper()),
                "color": str(item.get("color") or "BLUE"),
                "terminal": bool(item.get("terminal", False)),
                "hold": bool(item.get("hold", False)),
                "desktop": item.get("desktop") or None,
                "custom": True,
            }
        )
    return apps


def build_app_registry(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    registry = {key: dict(app) for key, app in APPS.items()}
    for app in cfg.get("custom_apps") or []:
        key = app.get("key")
        if isinstance(key, str) and key and key not in registry:
            registry[key] = dict(app)
    return registry


def normalize_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    cfg = _deep_merge(DEFAULT_CONFIG, raw or {})

    topics: list[str] = []
    raw_topics = cfg.get("topics")
    if isinstance(raw_topics, str):
        raw_topics = [raw_topics]
    for topic in raw_topics or []:
        if isinstance(topic, str):
            topic = topic.strip()
            if topic and topic.lower() not in {t.lower() for t in topics}:
                topics.append(topic)
    cfg["topics"] = (topics or list(DEFAULT_TOPICS))[:MAX_TOPICS]

    cfg["custom_apps"] = normalize_custom_apps(cfg.get("custom_apps"))
    registry = build_app_registry(cfg)
    cfg["pinned"] = [key for key in registry if key in (cfg.get("pinned") or [])]

    if cfg.get("units") not in {"metric", "imperial"}:
        cfg["units"] = "metric"
    if cfg.get("theme") not in THEMES:
        cfg["theme"] = "mocha"

    weather = cfg.get("weather")
    if not isinstance(weather, dict):
        weather = {}
        cfg["weather"] = weather
    weather["forecast_days"] = _clamp_int(
        weather.get("forecast_days"), 5, 1, 7
    )
    weather["refresh_minutes"] = _clamp_int(
        weather.get("refresh_minutes"), 15, 5, 120
    )
    for key in ("show_hourly", "show_forecast", "show_sun", "show_details"):
        weather[key] = bool(weather.get(key, True))

    loc = cfg.get("location")
    if not isinstance(loc, dict):
        loc = {}
        cfg["location"] = loc
    if loc.get("mode") not in {"auto", "manual"}:
        loc["mode"] = "auto"
    for key in ("city", "label"):
        if not isinstance(loc.get(key), str):
            loc[key] = ""
    return cfg


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return normalize_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    cfg = normalize_config(None)
    save_config(cfg)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def load_cache() -> dict[str, Any]:
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    return {}


def save_cache(cache: dict[str, Any]) -> None:
    cache["saved_at"] = datetime.now(timezone.utc).isoformat()
    try:
        CACHE_PATH.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Recently opened folders
# ---------------------------------------------------------------------------


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _timestamp(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def parse_xbel_folders(xml_text: str) -> list[dict[str, Any]]:
    """Return folder bookmarks from a GTK recently-used.xbel document."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    folders: list[dict[str, Any]] = []
    for node in root.iter():
        if _local_name(node.tag) != "bookmark":
            continue
        href = node.get("href") or ""
        if not href.startswith("file://"):
            continue
        path = Path(urllib.parse.unquote(urllib.parse.urlparse(href).path))
        if not path.is_dir():
            continue
        when = (
            node.get("visited") or node.get("modified") or node.get("added") or ""
        )
        name = "Home" if path == Path.home() else (path.name or str(path))
        folders.append(
            {
                "path": str(path),
                "name": name,
                "timestamp": _timestamp(when),
            }
        )
    return folders


def recent_folders(cache: dict[str, Any], limit: int = 5) -> list[dict[str, str]]:
    """Merge folders opened through Home Hub with desktop recent-folder history."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entry in cache.get("recent_folders") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        if not path or path in seen or not Path(path).is_dir():
            continue
        seen.add(path)
        home = str(Path.home())
        candidates.append(
            {
                "path": path,
                "name": "Home" if path == home else (Path(path).name or path),
                "timestamp": _timestamp(entry.get("opened")),
            }
        )

    xbel_files = [
        Path.home() / ".local" / "share" / "recently-used.xbel",
        Path.home() / ".recently-used.xbel",
    ]
    for xbel in xbel_files:
        if not xbel.exists():
            continue
        try:
            text = xbel.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for entry in parse_xbel_folders(text):
            if entry["path"] in seen:
                continue
            seen.add(entry["path"])
            candidates.append(entry)

    candidates.sort(key=lambda item: item["timestamp"], reverse=True)
    return [
        {"path": item["path"], "name": item["name"]}
        for item in candidates[:limit]
    ]


def record_recent_folder(
    cache: dict[str, Any], path: str, limit: int = 20
) -> None:
    target = str(Path(path))
    entries = [
        entry
        for entry in cache.get("recent_folders") or []
        if isinstance(entry, dict) and entry.get("path") != target
    ]
    entries.insert(
        0,
        {
            "path": target,
            "opened": datetime.now(timezone.utc).isoformat(),
        },
    )
    cache["recent_folders"] = entries[:limit]


def forget_recent_folder(cache: dict[str, Any], path: str) -> None:
    target = str(Path(path))
    cache["recent_folders"] = [
        entry
        for entry in cache.get("recent_folders") or []
        if isinstance(entry, dict) and entry.get("path") != target
    ]


# ---------------------------------------------------------------------------
# Time and text helpers
# ---------------------------------------------------------------------------


def relative_time(when: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seconds = (now - when).total_seconds()
    if seconds < 0:
        return "just now" if seconds > -300 else "soon"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def greeting_for(hour: int) -> str:
    if hour < 5:
        return "Good night"
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def format_day(day: datetime) -> str:
    return f"{day.strftime('%A, %B')} {day.day}, {day.year}"


def validate_topics(topics: list[str]) -> str | None:
    cleaned = [t.strip() for t in topics if t.strip()]
    if not cleaned:
        return "Add at least one news topic."
    if len(cleaned) > MAX_TOPICS:
        return f"Use at most {MAX_TOPICS} news topics."
    if len({t.lower() for t in cleaned}) != len(cleaned):
        return "Please choose different topics."
    return None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def http_get(url: str, timeout: float = 12.0, headers: dict[str, str] | None = None) -> str:
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    if requests is not None:
        response = requests.get(url, timeout=timeout, headers=request_headers)
        response.raise_for_status()
        return response.text
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read().decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------


@dataclass
class Article:
    topic: str
    title: str
    link: str
    source: str
    published: datetime

    def to_cache(self) -> dict[str, str]:
        return {
            "topic": self.topic,
            "title": self.title,
            "link": self.link,
            "source": self.source,
            "published": self.published.astimezone(timezone.utc).isoformat(),
        }


def article_from_cache(data: dict[str, Any]) -> Article | None:
    try:
        published = datetime.fromisoformat(str(data.get("published")))
    except (TypeError, ValueError):
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    title = str(data.get("title") or "").strip()
    link = str(data.get("link") or "").strip()
    if not title or not link:
        return None
    return Article(
        topic=str(data.get("topic") or ""),
        title=title,
        link=link,
        source=str(data.get("source") or ""),
        published=published,
    )


def parse_news(
    xml_text: str,
    topic: str,
    now: datetime | None = None,
    max_age_hours: int = NEWS_WINDOW_HOURS,
) -> list[Article]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    root = ET.fromstring(xml_text)
    articles: list[Article] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or "").strip()
        pub_text = (item.findtext("pubDate") or "").strip()
        if not title or not link or not pub_text:
            continue
        try:
            published = parsedate_to_datetime(pub_text)
        except (TypeError, ValueError):
            continue
        if published is None:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        published = published.astimezone(timezone.utc)
        age = now - published
        if age > timedelta(hours=max_age_hours) or age < timedelta(hours=-2):
            continue
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)].strip()
        if not title:
            continue
        articles.append(Article(topic, title, link, source, published))
    articles.sort(key=lambda article: article.published, reverse=True)
    return articles


def fetch_news_article(topic: str, now: datetime | None = None) -> Article | None:
    query = urllib.parse.quote(f"{topic} when:1d")
    url = (
        "https://news.google.com/rss/search?"
        f"q={query}&hl=en-US&gl=US&ceid=US:en"
    )
    articles = parse_news(http_get(url, timeout=12), topic, now=now)
    return articles[0] if articles else None


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------


def weather_info(code: int) -> tuple[str, str, str]:
    description, glyph, color_name = WEATHER_CODE_STYLES.get(
        int(code), ("Unknown conditions", "\u2022", "SUBTEXT1")
    )
    return description, glyph, globals().get(color_name, SUBTEXT1)


def geocode(city: str) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {"name": city, "count": 1, "language": "en", "format": "json"}
    )
    data = json.loads(
        http_get(
            "https://geocoding-api.open-meteo.com/v1/search?" + params, timeout=10
        )
    )
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"Could not find a place called \u201c{city}\u201d.")
    result = results[0]
    label_parts = [result.get("name"), result.get("country_code") or result.get("country")]
    return {
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "label": ", ".join(str(part) for part in label_parts if part),
    }


def detect_ip_location() -> dict[str, Any] | None:
    try:
        data = json.loads(http_get("https://ipapi.co/json/", timeout=6))
        latitude, longitude = data.get("latitude"), data.get("longitude")
        if latitude is not None and longitude is not None:
            label = ", ".join(
                str(part)
                for part in (data.get("city"), data.get("country_code"))
                if part
            )
            return {
                "latitude": latitude,
                "longitude": longitude,
                "label": label or str(data.get("country_name") or "Your location"),
            }
    except Exception:
        pass
    try:
        data = json.loads(http_get("https://ipinfo.io/json", timeout=6))
        location = data.get("loc")
        if location:
            latitude, longitude = (float(value) for value in location.split(","))
            label = ", ".join(
                str(part) for part in (data.get("city"), data.get("country")) if part
            )
            return {"latitude": latitude, "longitude": longitude, "label": label}
    except Exception:
        pass
    return None


def resolve_location(
    cfg: dict[str, Any], cached_location: dict[str, Any] | None = None
) -> dict[str, Any]:
    location = cfg.get("location", {})
    if location.get("mode") == "manual" and location.get("city"):
        if (
            location.get("latitude") is not None
            and location.get("longitude") is not None
            and location.get("label")
        ):
            return {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "label": location["label"],
            }
        return geocode(str(location["city"]))
    detected = detect_ip_location()
    if detected:
        return detected
    if cached_location and cached_location.get("latitude") is not None:
        return cached_location
    if location.get("latitude") is not None and location.get("longitude") is not None:
        return {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "label": location.get("label") or "Saved location",
        }
    return geocode(location.get("city") or "New York")


def get_weather(
    cfg: dict[str, Any], cached_location: dict[str, Any] | None = None
) -> dict[str, Any]:
    location = resolve_location(cfg, cached_location)
    imperial = cfg.get("units") == "imperial"
    forecast_days = _clamp_int(
        (cfg.get("weather") or {}).get("forecast_days"), 5, 1, 7
    )
    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
            "weather_code,wind_speed_10m"
        ),
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset"
        ),
        "hourly": "temperature_2m,precipitation_probability",
        "timezone": "auto",
        "forecast_days": forecast_days,
        "temperature_unit": "fahrenheit" if imperial else "celsius",
        "wind_speed_unit": "mph" if imperial else "kmh",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    data = json.loads(http_get(url, timeout=12))
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    code = int(current.get("weather_code", 0) or 0)
    description, glyph, color = weather_info(code)

    daily_items: list[dict[str, Any]] = []
    dates = daily.get("time") or []
    for index, date_text in enumerate(dates[:forecast_days]):
        try:
            day = datetime.strptime(date_text, "%Y-%m-%d")
            daily_code = int(daily["weather_code"][index])
            _, day_glyph, _ = weather_info(daily_code)
            daily_items.append(
                {
                    "label": day.strftime("%a"),
                    "glyph": day_glyph,
                    "high": round(float(daily["temperature_2m_max"][index])),
                    "low": round(float(daily["temperature_2m_min"][index])),
                }
            )
        except (KeyError, IndexError, TypeError, ValueError):
            continue

    hourly = data.get("hourly") or {}
    hourly_times = hourly.get("time") or []
    hourly_temps = hourly.get("temperature_2m") or []
    hourly_precip = hourly.get("precipitation_probability") or []
    now_hour = str(current.get("time") or "")[:13]
    start = 0
    if now_hour:
        for index, time_text in enumerate(hourly_times):
            if str(time_text)[:13] >= now_hour:
                start = index
                break
    hourly_items: list[dict[str, Any]] = []
    for index in range(start, min(start + 12, len(hourly_times))):
        try:
            temperature = round(float(hourly_temps[index]))
        except (IndexError, TypeError, ValueError):
            continue
        try:
            precipitation = round(float(hourly_precip[index]))
        except (IndexError, TypeError, ValueError):
            precipitation = None
        time_text = str(hourly_times[index])
        hourly_items.append(
            {
                "time": time_text.split("T", 1)[1][:5] if "T" in time_text else time_text,
                "temp": temperature,
                "precip": precipitation,
            }
        )

    sunrise = str((daily.get("sunrise") or [""])[0])
    sunset = str((daily.get("sunset") or [""])[0])

    def clock_part(value: str) -> str:
        return value.split("T", 1)[1][:5] if "T" in value else value

    return {
        "city": location.get("label") or "Your location",
        "location": location,
        "temperature": round(float(current.get("temperature_2m", 0))),
        "feels": round(float(current.get("apparent_temperature", 0))),
        "humidity": round(float(current.get("relative_humidity_2m", 0))),
        "wind": round(float(current.get("wind_speed_10m", 0))),
        "code": code,
        "description": description,
        "glyph": glyph,
        "color": color,
        "is_day": bool(current.get("is_day", 1)),
        "high": round(float((daily.get("temperature_2m_max") or [0])[0])),
        "low": round(float((daily.get("temperature_2m_min") or [0])[0])),
        "unit": "\u00b0F" if imperial else "\u00b0C",
        "wind_unit": "mph" if imperial else "km/h",
        "sunrise": clock_part(sunrise),
        "sunset": clock_part(sunset),
        "hourly": hourly_items,
        "daily": daily_items,
        "updated": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Launching apps
# ---------------------------------------------------------------------------


def find_executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if os.path.sep in name:
        path = Path(name).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    extra_dirs = [
        Path.home() / ".local" / "bin",
        Path.home() / ".opencode" / "bin",
        Path("/usr/local/bin"),
        Path("/usr/local/sbin"),
        Path("/usr/bin"),
        Path("/usr/sbin"),
    ]
    for directory in extra_dirs:
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def build_launch_command(
    key: str, apps: dict[str, dict[str, Any]] | None = None
) -> list[str]:
    app = (apps or APPS).get(key)
    if not app:
        return []
    command = list(app["launch"])
    executable = find_executable(command[0])
    if executable:
        command[0] = executable
    if app.get("terminal"):
        terminal = (
            find_executable("konsole")
            or find_executable("gnome-terminal")
            or find_executable("xfce4-terminal")
            or find_executable("alacritty")
            or find_executable("xterm")
        )
        if terminal:
            terminal_name = Path(terminal).name
            if "konsole" in terminal_name:
                prefix = [terminal, "--hold"] if app.get("hold") else [terminal]
                command = prefix + ["-e"] + command
            elif "gnome-terminal" in terminal_name:
                command = [terminal, "--"] + command
            else:
                command = [terminal, "-e"] + command
    return command


def launch_app(
    key: str,
    parent: tk.Misc | None = None,
    apps: dict[str, dict[str, Any]] | None = None,
) -> None:
    app = (apps or APPS).get(key)
    if not app:
        return
    command = build_launch_command(key, apps)
    try:
        subprocess.Popen(
            command,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            cwd=str(Path.home()),
        )
        return
    except (OSError, ValueError) as error:
        desktop = app.get("desktop")
        if desktop and find_executable("gtk-launch"):
            try:
                subprocess.Popen(
                    ["gtk-launch", desktop],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except OSError:
                pass
        if parent is not None:
            messagebox.showerror(
                "Home Hub",
                f"Could not launch {app['name']}.\n\n{error}\n\n"
                f"Command: {' '.join(command)}",
                parent=parent,
            )


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


def rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    **kwargs: Any,
) -> int:
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def recolor(widget: tk.Misc, old: str, new: str) -> None:
    try:
        if str(widget.cget("bg")).lower() == old.lower():
            widget.configure(bg=new)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        recolor(child, old, new)


def bind_tree(widget: tk.Misc, sequence: str, callback: Any) -> None:
    widget.bind(sequence, callback)
    for child in widget.winfo_children():
        bind_tree(child, sequence, callback)


class Card(tk.Canvas):
    """A flat panel with rounded corners and an embedded frame."""

    def __init__(
        self,
        master: tk.Misc,
        bg: str = SURFACE0,
        radius: int = 18,
        pad: int = 18,
        **kwargs: Any,
    ) -> None:
        parent_bg = str(master.cget("bg"))
        super().__init__(
            master, bg=parent_bg, highlightthickness=0, bd=0, **kwargs
        )
        self._bg = bg
        self._radius = radius
        self._pad = pad
        self.body = tk.Frame(self, bg=bg)
        self._window = self.create_window(pad, pad, anchor="nw", window=self.body)
        self.bind("<Configure>", self._on_resize)

    @property
    def color(self) -> str:
        return self._bg

    def _on_resize(self, event: tk.Event) -> None:
        self.delete("cardbg")
        rounded_rect(
            self, 0, 0, event.width, event.height, self._radius,
            fill=self._bg, outline="", tags="cardbg",
        )
        self.tag_lower("cardbg")
        width = max(1, event.width - 2 * self._pad)
        height = max(1, event.height - 2 * self._pad)
        self.itemconfigure(self._window, width=width, height=height)

    def set_bg(self, color: str) -> None:
        old = self._bg
        self._bg = color
        self.body.configure(bg=color)
        for child in self.body.winfo_children():
            recolor(child, old, color)
        self.delete("cardbg")
        width = self.winfo_width()
        height = self.winfo_height()
        if width > 1 and height > 1:
            rounded_rect(
                self, 0, 0, width, height, self._radius,
                fill=color, outline="", tags="cardbg",
            )
            self.tag_lower("cardbg")


class PillButton(tk.Label):
    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Any,
        bg: str | None = None,
        hover: str | None = None,
        fg: str | None = None,
        font: tuple[str, int, str] | None = None,
        padx: int = 16,
        pady: int = 8,
        **kwargs: Any,
    ) -> None:
        bg = bg or SURFACE0
        hover = hover or SURFACE1
        fg = fg or TEXT
        super().__init__(
            master,
            text=text,
            bg=bg,
            fg=fg,
            font=font or ui_font(10),
            padx=padx,
            pady=pady,
            cursor="hand2",
            **kwargs,
        )
        self._normal_bg = bg
        self._hover_bg = hover
        self._command = command
        self.bind("<Button-1>", lambda _event: self._command())
        self.bind("<Enter>", lambda _event: self.configure(bg=self._hover_bg))
        self.bind("<Leave>", lambda _event: self.configure(bg=self._normal_bg))


class ScrollFrame(tk.Frame):
    """A vertically scrollable frame used for long news and settings lists."""

    def __init__(self, master: tk.Misc, bg: str = BASE, **kwargs: Any) -> None:
        super().__init__(master, bg=bg, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = tk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview, width=8,
            bg=SURFACE0, troughcolor=bg, activebackground=SURFACE1,
            highlightthickness=0, bd=0, relief="flat",
        )
        self.body = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.body.bind("<Configure>", self._sync, add="+")
        self.canvas.bind("<Configure>", self._resize, add="+")

    def _sync(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _on_wheel(self, event: tk.Event) -> str:
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if getattr(event, "delta", 0) > 0 else 1
        self.canvas.yview_scroll(step * 3, "units")
        return "break"

    def bind_wheel(self) -> None:
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            bind_tree(self, sequence, self._on_wheel)


class NewsCard(Card):
    def __init__(self, master: tk.Misc, accent: str, **kwargs: Any) -> None:
        super().__init__(master, bg=SURFACE0, radius=16, pad=14, **kwargs)
        self.accent = accent
        self.topic = ""
        self.link: str | None = None
        self._headline_wrap = 640

        self.top = tk.Frame(self.body, bg=SURFACE0)
        self.top.pack(fill="x")
        self.chip = tk.Label(
            self.top, text="", font=ui_font(9, "bold"), fg=CRUST, bg=accent,
            padx=8, pady=2,
        )
        self.chip.pack(side="left")
        self.time_label = tk.Label(
            self.top, text="", font=ui_font(9), fg=OVERLAY1, bg=SURFACE0
        )
        self.time_label.pack(side="right")

        self.headline = tk.Label(
            self.body, text="", font=ui_font(13, "bold"), fg=TEXT, bg=SURFACE0,
            anchor="w", justify="left", wraplength=self._headline_wrap,
        )
        self.headline.pack(fill="x", pady=(6, 2))

        self.footer = tk.Frame(self.body, bg=SURFACE0)
        self.footer.pack(fill="x", side="bottom")
        self.meta = tk.Label(
            self.footer, text="", font=ui_font(9), fg=SUBTEXT0, bg=SURFACE0,
            anchor="w",
        )
        self.meta.pack(side="left")
        self.open_label = tk.Label(
            self.footer, text="", font=ui_font(9), fg=OVERLAY1, bg=SURFACE0,
            anchor="e",
        )
        self.open_label.pack(side="right")

        for widget in (self, self.body, self.top, self.chip, self.time_label,
                       self.headline, self.footer, self.meta, self.open_label):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", self.open_link)
            widget.bind("<Enter>", self._hover_on)
            widget.bind("<Leave>", self._hover_off)
        self.bind("<Configure>", self._wrap_headline, add="+")
        self.bind("<Configure>", self._adapt_layout, add="+")

    def _adapt_layout(self, event: tk.Event) -> None:
        if event.height < 126:
            if self.footer.winfo_manager():
                self.footer.pack_forget()
        elif not self.footer.winfo_manager():
            self.footer.pack(fill="x", side="bottom")

    def _hover_on(self, _event: tk.Event | None = None) -> None:
        self.set_bg(SURFACE1)

    def _hover_off(self, _event: tk.Event | None = None) -> None:
        self.set_bg(SURFACE0)

    def _wrap_headline(self, event: tk.Event) -> None:
        self._headline_wrap = max(220, event.width - 2 * self._pad - 8)
        self.headline.configure(wraplength=self._headline_wrap)

    def set_topic(self, topic: str, accent: str) -> None:
        self.topic = topic
        self.accent = accent
        self.chip.configure(text=topic.upper(), bg=accent)

    def show_article(
        self, article: Article, topic: str | None = None, stale: bool = False
    ) -> None:
        if topic:
            self.topic = topic
        self.link = article.link
        self.headline.configure(text=article.title, fg=TEXT)
        when = relative_time(article.published)
        self.time_label.configure(text=when, fg=OVERLAY1)
        source = article.source or "Google News"
        if stale:
            source += " \u00b7 cached"
        self.meta.configure(text=source, fg=SUBTEXT0)
        self.open_label.configure(text="Open article \u2192")

    def show_message(self, topic: str, headline: str, meta: str = "") -> None:
        self.topic = topic
        self.link = None
        self.headline.configure(text=headline, fg=SUBTEXT1)
        self.time_label.configure(text="\u2014", fg=OVERLAY0)
        self.meta.configure(text=meta, fg=OVERLAY1)
        self.open_label.configure(text="")

    def open_link(self, _event: tk.Event | None = None) -> None:
        if not self.link:
            return
        try:
            webbrowser.open_new_tab(self.link)
        except Exception:
            pass


class AppTile(Card):
    def __init__(
        self,
        master: tk.Misc,
        key: str,
        app: dict[str, Any],
        icon: Any,
        on_unpin: Any,
        apps: dict[str, dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master, bg=SURFACE0, radius=16, pad=8, width=96, height=96, **kwargs
        )
        self.key = key
        self.app = app
        self.icon = icon
        self._on_unpin = on_unpin
        self.apps = apps or APPS

        holder = tk.Frame(self.body, bg=SURFACE0, width=40, height=40)
        holder.pack(pady=(2, 4))
        holder.pack_propagate(False)
        if icon is not None:
            label = tk.Label(holder, image=icon, bg=SURFACE0, bd=0)
        else:
            label = tk.Label(
                holder, text=app["monogram"], font=ui_font(15, "bold"),
                fg=resolve_color(app.get("color")), bg=SURFACE0, bd=0,
            )
        label.place(relx=0.5, rely=0.5, anchor="center")

        name = tk.Label(
            self.body, text=app["name"], font=ui_font(9), fg=SUBTEXT1, bg=SURFACE0
        )
        name.pack()

        bind_tree(
            self, "<Button-1>",
            lambda _event: launch_app(
                self.key, self.winfo_toplevel(), self.apps
            ),
        )
        bind_tree(self, "<Button-3>", self._show_menu)
        bind_tree(self, "<Enter>", lambda _event: self.set_bg(SURFACE1))
        bind_tree(self, "<Leave>", lambda _event: self.set_bg(SURFACE0))
        for widget in [self, holder, label, name]:
            widget.configure(cursor="hand2")

    def _show_menu(self, event: tk.Event) -> None:
        menu = tk.Menu(
            self, tearoff=0, bg=SURFACE0, fg=TEXT, bd=0,
            activebackground=SURFACE1, activeforeground=TEXT,
        )
        menu.add_command(
            label=f"Launch {self.app['name']}",
            command=lambda: launch_app(
                self.key, self.winfo_toplevel(), self.apps
            ),
        )
        menu.add_separator()
        menu.add_command(label="Unpin", command=self._on_unpin)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class HubApp:
    def __init__(self, root: tk.Tk, cfg: dict[str, Any]) -> None:
        global UI_FONT, MONO_FONT
        self.root = root
        self.cfg = cfg
        self.apps = build_app_registry(cfg)
        self.cache = load_cache()
        self.queue: queue.Queue = queue.Queue()
        self.generation = 0
        self.pending = 0
        self.had_error = False
        self.icons: dict[str, Any] = {}
        self.news_cards: list[NewsCard] = []
        self.last_status = ""
        self._refresh_job: str | None = None

        families = set(tkfont.families(root))
        for candidate in ("Inter", "Noto Sans", "Cantarell", "DejaVu Sans", "Liberation Sans"):
            if candidate in families:
                UI_FONT = candidate
                break
        for candidate in ("JetBrains Mono", "Hack", "DejaVu Sans Mono", "Liberation Mono"):
            if candidate in families:
                MONO_FONT = candidate
                break

        root.title("Home Hub")
        root.configure(bg=BASE)
        self._window_icon = None
        icon_path = APP_DIR / "assets" / "home-hub.png"
        if icon_path.exists() and Image is not None and ImageTk is not None:
            try:
                icon = Image.open(icon_path).convert("RGBA")
                icon.thumbnail((64, 64), Image.LANCZOS)
                self._window_icon = ImageTk.PhotoImage(icon)
                root.iconphoto(True, self._window_icon)
            except Exception:
                pass
        self._place_window()

        self._build_header()
        self._build_content()

        root.bind("<F11>", self._toggle_fullscreen)
        root.bind("<Escape>", self._leave_fullscreen)
        root.bind("<Control-r>", lambda _event: self.refresh_all())
        root.bind("<Control-comma>", lambda _event: self.open_settings())
        root.protocol("WM_DELETE_WINDOW", root.destroy)

        self._load_cached_into_ui()
        self.tick()
        self.refresh_all()
        self.root.after(250, self._poll_queue)
        self._schedule_periodic_refresh()

    # -- layout ---------------------------------------------------------

    def _place_window(self) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(screen_w - 60, max(1180, min(2200, int(screen_w * 0.72))))
        height = min(screen_h - 80, max(760, min(1040, int(screen_h * 0.62))))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min(1180, screen_w - 40), min(760, screen_h - 60))

    def _rebuild_ui(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        self.news_cards = []
        self.weather_extras = None
        self.cfg = normalize_config(self.cfg)
        self.apps = build_app_registry(self.cfg)
        apply_theme(self.cfg.get("theme", "mocha"))
        self.root.configure(bg=BASE)
        self._build_header()
        self._build_content()
        self._load_cached_into_ui()
        self.refresh_all()

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=BASE)
        header.pack(fill="x", padx=36, pady=(22, 6))

        left = tk.Frame(header, bg=BASE)
        left.pack(side="left")
        self.greeting_label = tk.Label(
            left, text="", font=ui_font(11), fg=SUBTEXT0, bg=BASE, anchor="w"
        )
        self.greeting_label.pack(anchor="w")
        self.clock_label = tk.Label(
            left, text="", font=mono_font(40, "bold"), fg=TEXT, bg=BASE, anchor="w"
        )
        self.clock_label.pack(anchor="w")
        self.date_label = tk.Label(
            left, text="", font=ui_font(11), fg=SUBTEXT0, bg=BASE, anchor="w"
        )
        self.date_label.pack(anchor="w")

        right = tk.Frame(header, bg=BASE)
        right.pack(side="right", anchor="ne")
        self.status_label = tk.Label(
            right, text="Starting\u2026", font=ui_font(9), fg=OVERLAY0, bg=BASE,
            anchor="e",
        )
        self.status_label.pack(anchor="e", pady=(0, 8))
        buttons = tk.Frame(right, bg=BASE)
        buttons.pack(anchor="e")
        PillButton(buttons, "Refresh", self.refresh_all).pack(side="left", padx=(0, 8))
        PillButton(buttons, "Settings", self.open_settings).pack(side="left")

    def _build_content(self) -> None:
        content = tk.Frame(self.root, bg=BASE)
        content.pack(fill="both", expand=True, padx=36, pady=(4, 4))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=0, minsize=356)
        content.rowconfigure(0, weight=1)

        # Left column: news articles and recently opened folders.
        left = tk.Frame(content, bg=BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        news_header = tk.Frame(left, bg=BASE)
        news_header.grid(row=0, column=0, sticky="ew")
        tk.Label(
            news_header, text="Latest news", font=ui_font(14, "bold"),
            fg=TEXT, bg=BASE,
        ).pack(side="left")
        self.topic_count_label = tk.Label(
            news_header, text="", font=ui_font(9), fg=GREEN, bg=BASE,
        )
        self.topic_count_label.pack(side="right")

        self.news_scroll = ScrollFrame(left, bg=BASE)
        self.news_scroll.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.news_body = self.news_scroll.body
        self._build_news_cards()

        self.folders_card = Card(
            left, bg=SURFACE0, radius=20, pad=16, height=176
        )
        self.folders_card.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self._build_folders(self.folders_card.body)

        # Right column: weather and app shortcuts.
        right = tk.Frame(content, bg=BASE)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.weather_card = Card(right, bg=SURFACE0, radius=20, pad=22)
        self.weather_card.grid(row=0, column=0, sticky="nsew")
        self.weather_body = self.weather_card.body
        self.weather_extras: tk.Frame | None = None
        self.weather_card.bind("<Configure>", self._on_weather_resize, add="+")

        self.shortcuts_card = Card(
            right, bg=SURFACE0, radius=20, pad=18, height=272
        )
        self.shortcuts_card.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self._build_shortcuts(self.shortcuts_card.body)

    def _build_news_cards(self) -> None:
        for child in self.news_body.winfo_children():
            child.destroy()
        self.news_cards = []
        for index, topic in enumerate(self.cfg["topics"]):
            accent = TOPIC_COLORS[index % len(TOPIC_COLORS)]
            card = NewsCard(self.news_body, accent, height=138)
            card.pack(fill="x", pady=5)
            card.set_topic(topic, accent)
            card.show_message(topic, "Loading\u2026")
            self.news_cards.append(card)
        self.news_scroll.bind_wheel()
        if hasattr(self, "topic_count_label"):
            count = len(self.cfg["topics"])
            noun = "topic" if count == 1 else "topics"
            self.topic_count_label.configure(
                text=f"\u25cf  {count} {noun} \u00b7 last 24 hours"
            )

    def _build_folders(self, parent: tk.Misc) -> None:
        header = tk.Frame(parent, bg=SURFACE0)
        header.pack(fill="x")
        tk.Label(
            header, text="Recent folders", font=ui_font(12, "bold"),
            fg=TEXT, bg=SURFACE0,
        ).pack(side="left")
        PillButton(
            header, "Browse\u2026", self._browse_folder, padx=8, pady=3,
            font=ui_font(8),
        ).pack(side="right")

        self.folders_frame = tk.Frame(parent, bg=SURFACE0)
        self.folders_frame.pack(fill="both", expand=True, pady=(8, 0))
        self._rebuild_folders()

    def _rebuild_folders(self) -> None:
        if not hasattr(self, "folders_frame"):
            return
        for child in self.folders_frame.winfo_children():
            child.destroy()
        folders = recent_folders(self.cache, limit=5)
        if not folders:
            tk.Label(
                self.folders_frame,
                text="No recent folders yet. Use \u201cBrowse\u2026\u201d to open one.",
                font=ui_font(9), fg=OVERLAY1, bg=SURFACE0, anchor="w",
            ).pack(fill="x", pady=4)
        for folder in folders:
            path = folder["path"]
            display = path.replace(str(Path.home()), "~", 1)
            if len(display) > 34:
                display = "\u2026" + display[-33:]
            row = tk.Frame(self.folders_frame, bg=SURFACE0)
            row.pack(fill="x", pady=1)
            glyph = tk.Label(
                row, text="\u25b8", font=ui_font(10, "bold"), fg=PEACH,
                bg=SURFACE0,
            )
            glyph.pack(side="left")
            name = tk.Label(
                row, text=folder["name"], font=ui_font(9), fg=SUBTEXT1,
                bg=SURFACE0, anchor="w",
            )
            name.pack(side="left", padx=(4, 8))
            path_label = tk.Label(
                row, text=display, font=ui_font(8), fg=OVERLAY1, bg=SURFACE0,
                anchor="e",
            )
            path_label.pack(side="right")
            for widget in (row, glyph, name, path_label):
                widget.configure(cursor="hand2")
                widget.bind(
                    "<Button-1>", lambda _event, p=path: self._open_folder(p)
                )
        rows = max(1, len(folders))
        self.folders_card.configure(height=max(132, min(250, 82 + rows * 28)))

    def _open_folder(self, path: str) -> None:
        target = Path(path).expanduser()
        if not target.is_dir():
            messagebox.showerror(
                "Home Hub", f"Folder not found:\n{target}", parent=self.root
            )
            return
        try:
            subprocess.Popen(
                ["xdg-open", str(target)],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except OSError as error:
            messagebox.showerror(
                "Home Hub", f"Could not open the folder.\n\n{error}",
                parent=self.root,
            )
            return
        record_recent_folder(self.cache, str(target))
        save_cache(self.cache)
        self._rebuild_folders()

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(
            parent=self.root, initialdir=str(Path.home()), mustexist=True
        )
        if path:
            self._open_folder(path)

    def _build_shortcuts(self, parent: tk.Misc) -> None:
        header = tk.Frame(parent, bg=SURFACE0)
        header.pack(fill="x")
        tk.Label(
            header, text="Shortcuts", font=ui_font(12, "bold"), fg=TEXT, bg=SURFACE0
        ).pack(side="left")
        PillButton(
            header, "Edit pins", self._show_pin_menu, padx=10, pady=4,
            font=ui_font(9),
        ).pack(side="right")

        self.tiles_scroll = ScrollFrame(parent, bg=SURFACE0)
        self.tiles_scroll.pack(fill="both", expand=True, pady=(10, 0))
        self.tiles_frame = self.tiles_scroll.body
        self._rebuild_tiles()

    # -- cached data ----------------------------------------------------

    def _load_cached_into_ui(self) -> None:
        weather = self.cache.get("weather")
        if isinstance(weather, dict) and weather.get("temperature") is not None:
            self.render_weather(weather, stale=True)
        cached_news = self.cache.get("news") or {}
        if isinstance(cached_news, dict):
            for index, topic in enumerate(self.cfg["topics"]):
                data = cached_news.get(topic)
                article = article_from_cache(data) if isinstance(data, dict) else None
                if article:
                    self.news_cards[index].show_article(
                        article, topic=topic, stale=True
                    )

    # -- clock ----------------------------------------------------------

    def tick(self) -> None:
        now = datetime.now()
        self.clock_label.configure(text=now.strftime("%H:%M:%S"))
        self.greeting_label.configure(text=greeting_for(now.hour))
        self.date_label.configure(text=format_day(now))
        self.root.after(1000, self.tick)

    # -- refresh --------------------------------------------------------

    def refresh_all(self) -> None:
        self.generation += 1
        generation = self.generation
        config_snapshot = json.loads(json.dumps(self.cfg))
        topics = list(config_snapshot["topics"])
        self.pending = 1 + len(topics)
        self.had_error = False
        self.status_label.configure(text="Updating\u2026", fg=OVERLAY1)
        cached_location = self.cache.get("location")

        threading.Thread(
            target=self._weather_worker,
            args=(generation, config_snapshot, cached_location),
            daemon=True,
        ).start()
        for topic in topics:
            threading.Thread(
                target=self._news_worker, args=(generation, topic), daemon=True
            ).start()

    def _weather_worker(
        self,
        generation: int,
        cfg: dict[str, Any],
        cached_location: dict[str, Any] | None,
    ) -> None:
        try:
            data = get_weather(cfg, cached_location)
            self.queue.put(("weather", generation, data, None))
        except Exception as error:
            self.queue.put(("weather", generation, None, str(error)))

    def _news_worker(self, generation: int, topic: str) -> None:
        try:
            article = fetch_news_article(topic)
            self.queue.put(("news", generation, topic, article, None))
        except Exception as error:
            self.queue.put(("news", generation, topic, None, str(error)))

    def _schedule_periodic_refresh(self) -> None:
        if self._refresh_job is not None:
            try:
                self.root.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
        minutes = _clamp_int(
            (self.cfg.get("weather") or {}).get("refresh_minutes"), 15, 5, 120
        )
        self._refresh_job = self.root.after(
            minutes * 60 * 1000, self._periodic_refresh
        )

    def _periodic_refresh(self) -> None:
        self._refresh_job = None
        self.refresh_all()
        self._schedule_periodic_refresh()

    def _poll_queue(self) -> None:
        try:
            while True:
                message = self.queue.get_nowait()
                kind, generation = message[0], message[1]
                if generation != self.generation:
                    continue
                if kind == "weather":
                    _, _, data, error = message
                    self._apply_weather(data, error)
                elif kind == "news":
                    _, _, topic, article, error = message
                    self._apply_news(topic, article, error)
                self.pending -= 1
                if self.pending <= 0:
                    self._finish_refresh()
        except queue.Empty:
            pass
        self.root.after(250, self._poll_queue)

    def _apply_weather(self, data: dict[str, Any] | None, error: str | None) -> None:
        if data:
            self.cache["weather"] = data
            if isinstance(data.get("location"), dict):
                self.cache["location"] = data["location"]
            self.render_weather(data)
            save_cache(self.cache)
            return
        self.had_error = True
        cached = self.cache.get("weather")
        if isinstance(cached, dict) and cached.get("temperature") is not None:
            self.render_weather(cached, stale=True)
        else:
            self.render_weather(None, error=error)

    def _apply_news(
        self,
        topic: str,
        article: Article | None,
        error: str | None,
    ) -> None:
        index = self._topic_index(topic)
        if index < 0:
            return
        card = self.news_cards[index]
        if article:
            cache_news = self.cache.setdefault("news", {})
            if not isinstance(cache_news, dict):
                cache_news = {}
                self.cache["news"] = cache_news
            cache_news[topic] = article.to_cache()
            card.show_article(article, topic=topic)
            save_cache(self.cache)
            return
        if error:
            self.had_error = True
            cached = self.cache.get("news")
            cached_data = cached.get(topic) if isinstance(cached, dict) else None
            cached_article = (
                article_from_cache(cached_data) if isinstance(cached_data, dict) else None
            )
            if cached_article:
                card.show_article(cached_article, topic=topic, stale=True)
            else:
                card.show_message(topic, "Couldn't load this topic", error)
            return
        card.show_message(topic, "No articles in the last 24 hours", "Try again later")

    def _finish_refresh(self) -> None:
        stamp = datetime.now().strftime("%H:%M")
        suffix = " \u00b7 offline" if self.had_error else ""
        self.last_status = f"Updated {stamp}{suffix}"
        self.status_label.configure(
            text=self.last_status, fg=PEACH if self.had_error else OVERLAY0
        )
        self._rebuild_folders()

    def _topic_index(self, topic: str) -> int:
        try:
            return self.cfg["topics"].index(topic)
        except ValueError:
            return -1

    # -- rendering ------------------------------------------------------

    def _on_weather_resize(self, event: tk.Event) -> None:
        extras = self.weather_extras
        if extras is None or not extras.winfo_exists():
            return
        if event.height < 420:
            if extras.winfo_manager():
                extras.pack_forget()
        elif not extras.winfo_manager():
            extras.pack(fill="both", expand=True)

    def render_weather(
        self,
        data: dict[str, Any] | None,
        stale: bool = False,
        error: str | None = None,
    ) -> None:
        self.weather_extras = None
        for child in self.weather_body.winfo_children():
            child.destroy()
        options = self.cfg.get("weather") or {}
        show_details = bool(options.get("show_details", True))
        show_hourly = bool(options.get("show_hourly", True))
        show_sun = bool(options.get("show_sun", True))
        show_forecast = bool(options.get("show_forecast", True))
        forecast_days = _clamp_int(options.get("forecast_days"), 5, 1, 7)

        if not data:
            wrapper = tk.Frame(self.weather_body, bg=SURFACE0)
            wrapper.pack(expand=True, fill="both")
            tk.Label(
                wrapper, text="Weather unavailable", font=ui_font(16, "bold"),
                fg=TEXT, bg=SURFACE0,
            ).pack(pady=(60, 6))
            tk.Label(
                wrapper, text=error or "Check your connection.", font=ui_font(10),
                fg=OVERLAY1, bg=SURFACE0, wraplength=290, justify="center",
            ).pack()
            tk.Label(
                wrapper, text="Set a city in Settings if this keeps happening.",
                font=ui_font(9), fg=OVERLAY0, bg=SURFACE0, wraplength=290,
                justify="center",
            ).pack(pady=(10, 0))
            return

        city_row = tk.Frame(self.weather_body, bg=SURFACE0)
        city_row.pack(fill="x")
        tk.Label(
            city_row, text=data.get("city", "Your location"), font=ui_font(14, "bold"),
            fg=TEXT, bg=SURFACE0, anchor="w",
        ).pack(side="left")
        note = "cached" if stale else "live"
        tk.Label(
            city_row, text=note, font=ui_font(9), fg=OVERLAY1, bg=SURFACE0
        ).pack(side="right")

        hero = tk.Frame(self.weather_body, bg=SURFACE0)
        hero.pack(fill="x", pady=(10, 0))
        tk.Label(
            hero, text=data.get("glyph", "\u2022"), font=(UI_FONT, 38),
            fg=data.get("color", SUBTEXT1), bg=SURFACE0,
        ).pack(side="left", padx=(0, 12))
        temperature = tk.Frame(hero, bg=SURFACE0)
        temperature.pack(side="left", anchor="w")
        tk.Label(
            temperature,
            text=f"{data.get('temperature', 0)}{data.get('unit', '\u00b0C')}",
            font=ui_font(40, "bold"), fg=TEXT, bg=SURFACE0, anchor="w",
        ).pack(anchor="w")
        tk.Label(
            temperature, text=data.get("description", ""), font=ui_font(11),
            fg=SUBTEXT1, bg=SURFACE0, anchor="w",
        ).pack(anchor="w")

        if show_details:
            stats = tk.Frame(self.weather_body, bg=SURFACE0)
            stats.pack(fill="x", pady=(16, 0))
            stats.columnconfigure(0, weight=1)
            stats.columnconfigure(1, weight=1)
            stat_values = [
                ("Feels like", f"{data.get('feels', 0)}\u00b0"),
                ("Humidity", f"{data.get('humidity', 0)}%"),
                ("Wind", f"{data.get('wind', 0)} {data.get('wind_unit', '')}"),
                ("High / Low", f"{data.get('high', 0)}\u00b0 / {data.get('low', 0)}\u00b0"),
            ]
            for index, (label, value) in enumerate(stat_values):
                cell = tk.Frame(stats, bg=SURFACE0)
                cell.grid(
                    row=index // 2, column=index % 2, sticky="w",
                    padx=(0, 12), pady=(0, 8),
                )
                tk.Label(
                    cell, text=label, font=ui_font(9), fg=OVERLAY1, bg=SURFACE0,
                    anchor="w",
                ).pack(anchor="w")
                tk.Label(
                    cell, text=value, font=ui_font(12, "bold"), fg=SUBTEXT1,
                    bg=SURFACE0, anchor="w",
                ).pack(anchor="w")

        hourly = data.get("hourly") or []
        daily = data.get("daily") or []
        has_sun = bool(data.get("sunrise") or data.get("sunset"))
        if show_hourly and not hourly:
            show_hourly = False
        if show_sun and not has_sun:
            show_sun = False
        if show_forecast and not daily:
            show_forecast = False

        extras: tk.Frame | None = None
        if show_hourly or show_sun or show_forecast:
            extras = tk.Frame(self.weather_body, bg=SURFACE0)
            self.weather_extras = extras
            extras.pack(fill="both", expand=True)

        if extras is None:
            return

        if show_hourly and hourly:
            tk.Label(
                extras, text="Next 12 hours", font=ui_font(9),
                fg=OVERLAY1, bg=SURFACE0, anchor="w",
            ).pack(fill="x", pady=(12, 0))
            chart = tk.Canvas(
                extras, height=104, bg=SURFACE0,
                highlightthickness=0, bd=0,
            )
            chart.pack(fill="x", pady=(2, 0))

            def draw_hourly(
                _event: tk.Event | None = None,
                canvas: tk.Canvas = chart,
                items: list[dict[str, Any]] = hourly,
            ) -> None:
                canvas.delete("all")
                width = canvas.winfo_width()
                height = int(float(canvas.cget("height")))
                if width <= 2 or not items:
                    return
                left, right, top, bottom = 22, 12, 16, 28
                temps = [item["temp"] for item in items]
                low, high = min(temps), max(temps)
                span = max(1, high - low)
                step = (width - left - right) / max(1, len(items) - 1)
                points = []
                for index, item in enumerate(items):
                    x = left + index * step
                    y = top + (high - item["temp"]) / span * (height - top - bottom)
                    points.append((x, y))
                if len(points) > 1:
                    canvas.create_line(
                        [coord for point in points for coord in point],
                        fill=BLUE, width=2, smooth=True,
                    )
                for index, (x, y) in enumerate(points):
                    canvas.create_oval(
                        x - 2, y - 2, x + 2, y + 2, fill=SKY, outline=""
                    )
                    if index % 3 == 0 or index == len(points) - 1:
                        canvas.create_text(
                            x, y - 10, text=f"{items[index]['temp']}\u00b0",
                            fill=SUBTEXT1, font=ui_font(8),
                        )
                        canvas.create_text(
                            x, height - 10, text=items[index]["time"],
                            fill=OVERLAY1, font=ui_font(8),
                        )

            chart.bind("<Configure>", draw_hourly)

        if show_sun:
            tk.Frame(extras, bg=SURFACE1, height=1).pack(
                fill="x", pady=(8, 10)
            )
            tk.Label(
                extras,
                text=f"Sunrise {data.get('sunrise', '\u2014')}   \u00b7   "
                     f"Sunset {data.get('sunset', '\u2014')}",
                font=ui_font(9), fg=OVERLAY1, bg=SURFACE0, anchor="w",
            ).pack(fill="x")

        if show_forecast:
            tk.Frame(extras, bg=SURFACE0).pack(fill="both", expand=True)
            forecast = tk.Frame(extras, bg=SURFACE0)
            forecast.pack(fill="x", pady=(14, 0))
            for index, day in enumerate(daily[:forecast_days]):
                forecast.columnconfigure(index, weight=1)
                cell = tk.Frame(forecast, bg=SURFACE0)
                cell.grid(row=0, column=index, sticky="nsew", padx=(0, 4))
                tk.Label(
                    cell, text=day.get("label", ""), font=ui_font(9),
                    fg=OVERLAY1, bg=SURFACE0,
                ).pack()
                tk.Label(
                    cell, text=day.get("glyph", "\u2022"), font=(UI_FONT, 18),
                    fg=SUBTEXT1, bg=SURFACE0,
                ).pack()
                tk.Label(
                    cell,
                    text=f"{day.get('high', 0)}\u00b0 / {day.get('low', 0)}\u00b0",
                    font=ui_font(9), fg=SUBTEXT1, bg=SURFACE0,
                ).pack()

    # -- icon loading ---------------------------------------------------

    def _load_icon(self, name: str | None, size: int = 44) -> Any:
        if not name or Image is None or ImageTk is None:
            return None
        if name in self.icons:
            return self.icons[name]
        path = self._find_icon(name)
        if not path:
            self.icons[name] = None
            return None
        try:
            image = Image.open(path).convert("RGBA")
            image.thumbnail((size, size), Image.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.paste(
                image,
                ((size - image.width) // 2, (size - image.height) // 2),
                image,
            )
            photo = ImageTk.PhotoImage(canvas)
            self.icons[name] = photo
            return photo
        except Exception:
            self.icons[name] = None
            return None

    def _find_icon(self, name: str) -> str | None:
        explicit = Path(name).expanduser()
        if explicit.is_file():
            return str(explicit)
        home = str(Path.home())
        suffix = explicit.suffix.lower()
        icon = name if suffix in {".png", ".jpg", ".jpeg", ".xpm"} else f"{name}.png"
        patterns = [
            f"{home}/.local/share/icons/*/*/apps/{icon}",
            f"/var/lib/flatpak/exports/share/icons/*/*/apps/{icon}",
            f"/var/lib/flatpak/appstream/*/*/*/icons/*/{icon}",
            f"/usr/share/icons/*/*/apps/{icon}",
            f"/usr/share/icons/*/{icon}",
            f"/usr/share/pixmaps/{icon}",
        ]
        matches: list[tuple[int, str]] = []
        for pattern in patterns:
            for path in glob.glob(pattern):
                if not os.path.isfile(path):
                    continue
                size_match = re.search(r"/(\d+)x\d+/", path)
                size = int(size_match.group(1)) if size_match else 0
                matches.append((size, path))
        if not matches:
            return None
        usable = [item for item in matches if item[0] >= 64]
        pool = usable or matches
        pool.sort(key=lambda item: abs(item[0] - 128) if item[0] else 10_000)
        return pool[0][1]

    # -- shortcuts ------------------------------------------------------

    def _rebuild_tiles(self) -> None:
        for child in self.tiles_frame.winfo_children():
            child.destroy()
        for index in range(3):
            self.tiles_frame.columnconfigure(index, weight=1)
        pinned = [
            key for key in self.apps if key in (self.cfg.get("pinned") or [])
        ]

        if not pinned:
            self.shortcuts_card.configure(height=150)
            tk.Label(
                self.tiles_frame,
                text="No pinned apps yet \u2014 use \u201cEdit pins\u201d to add some.",
                font=ui_font(9), fg=OVERLAY1, bg=SURFACE0, wraplength=250,
                justify="center",
            ).pack(pady=20)
            self.tiles_scroll.bind_wheel()
            return

        for index, key in enumerate(pinned):
            app = self.apps[key]
            icon = self._load_icon(app.get("icon"), size=40)
            tile = AppTile(
                self.tiles_frame, key, app, icon,
                on_unpin=lambda k=key: self.set_pin(k, False),
                apps=self.apps,
            )
            tile.grid(
                row=index // 3, column=index % 3, padx=2, pady=2,
            )

        rows = (len(pinned) + 2) // 3
        wanted = 72 + rows * 96 + (rows - 1) * 8
        self.shortcuts_card.configure(height=min(380, wanted))
        self.tiles_scroll.bind_wheel()

    def _show_pin_menu(self, event: tk.Event | None = None) -> None:
        menu = tk.Menu(
            self.root, tearoff=0, bg=SURFACE0, fg=TEXT, bd=0,
            activebackground=SURFACE1, activeforeground=TEXT,
            selectcolor=SURFACE1,
        )
        for key, app in self.apps.items():
            variable = tk.BooleanVar(value=key in self.cfg["pinned"])
            menu.add_checkbutton(
                label=app["name"], variable=variable,
                command=lambda k=key, v=variable: self.set_pin(k, v.get()),
                bg=SURFACE0, fg=TEXT, activebackground=SURFACE1,
                activeforeground=TEXT, selectcolor=SURFACE1,
            )
        try:
            if event is not None:
                menu.tk_popup(event.x_root, event.y_root)
            else:
                menu.tk_popup(*self.root.winfo_pointerxy())
        finally:
            menu.grab_release()

    def set_pin(self, key: str, pinned: bool) -> None:
        current = list(self.cfg.get("pinned") or [])
        if pinned and key not in current:
            current.append(key)
        elif not pinned and key in current:
            current.remove(key)
        self.cfg["pinned"] = [k for k in self.apps if k in current]
        save_config(self.cfg)
        self._rebuild_tiles()

    # -- settings -------------------------------------------------------

    def open_settings(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Home Hub settings")
        window.configure(bg=BASE)
        window.transient(self.root)
        window.resizable(True, True)
        window.grab_set()
        width, height = 640, 780
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.minsize(560, 560)

        container = tk.Frame(window, bg=BASE, padx=26, pady=20)
        container.pack(fill="both", expand=True)

        tk.Label(
            container, text="Settings", font=ui_font(20, "bold"), fg=TEXT, bg=BASE,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            container,
            text="Themes, weather display, news topics, folders and shortcuts.",
            font=ui_font(9), fg=OVERLAY1, bg=BASE, anchor="w",
        ).pack(fill="x", pady=(2, 8))

        scroll = ScrollFrame(container, bg=BASE)
        scroll.pack(fill="both", expand=True)
        form = scroll.body

        def section(text: str, hint: str = "") -> None:
            tk.Label(
                form, text=text, font=ui_font(11, "bold"), fg=SUBTEXT1,
                bg=BASE, anchor="w",
            ).pack(fill="x", pady=(14, 2))
            if hint:
                tk.Label(
                    form, text=hint, font=ui_font(9), fg=OVERLAY1, bg=BASE,
                    anchor="w", justify="left",
                ).pack(fill="x", pady=(0, 3))

        def checkbutton(parent: tk.Misc, text: str, variable: tk.BooleanVar) -> None:
            tk.Checkbutton(
                parent, text=text, variable=variable,
                bg=BASE, fg=SUBTEXT0, activebackground=BASE,
                activeforeground=TEXT, selectcolor=SURFACE0,
                highlightthickness=0, bd=0, font=ui_font(10), anchor="w",
            ).pack(anchor="w", pady=1)

        # -- appearance --------------------------------------------------
        section("Appearance")
        theme_key_by_label = {label: key for key, label in THEME_LABELS.items()}
        theme_var = tk.StringVar(
            value=THEME_LABELS.get(self.cfg.get("theme", "mocha"), "Catppuccin Mocha")
        )
        theme_row = tk.Frame(form, bg=BASE)
        theme_row.pack(fill="x", pady=(2, 0))
        theme_menu = tk.OptionMenu(
            theme_row, theme_var, *theme_key_by_label.keys()
        )
        theme_menu.configure(
            bg=SURFACE0, fg=TEXT, activebackground=SURFACE1,
            activeforeground=TEXT, highlightthickness=0, bd=0,
            font=ui_font(10), indicatoron=True, anchor="w", width=26,
        )
        theme_menu["menu"].configure(
            bg=SURFACE0, fg=TEXT, activebackground=SURFACE1,
            activeforeground=TEXT, font=ui_font(10),
        )
        theme_menu.pack(side="left")

        # -- location ----------------------------------------------------
        section("Location")
        mode_var = tk.StringVar(value=self.cfg["location"].get("mode", "auto"))
        mode_row = tk.Frame(form, bg=BASE)
        mode_row.pack(fill="x", pady=(2, 4))
        for value, label in (("auto", "Auto-detect"), ("manual", "Use this city")):
            tk.Radiobutton(
                mode_row, text=label, variable=mode_var, value=value,
                bg=BASE, fg=SUBTEXT0, activebackground=BASE, activeforeground=TEXT,
                selectcolor=SURFACE0, highlightthickness=0, bd=0,
                font=ui_font(10),
            ).pack(side="left", padx=(0, 14))
        city_var = tk.StringVar(value=self.cfg["location"].get("city", ""))
        city_entry = self._entry(form, city_var)
        city_entry.pack(fill="x", pady=(0, 2))

        # -- weather -----------------------------------------------------
        section("Weather", "Choose what the weather card shows and how often it refreshes.")
        weather_cfg = self.cfg.get("weather") or {}
        weather_vars: dict[str, tk.BooleanVar] = {}
        for key, label in (
            ("show_details", "Show feels-like, humidity, wind and high/low"),
            ("show_hourly", "Show the next 12 hours chart"),
            ("show_forecast", "Show the daily forecast"),
            ("show_sun", "Show sunrise and sunset"),
        ):
            variable = tk.BooleanVar(value=bool(weather_cfg.get(key, True)))
            weather_vars[key] = variable
            checkbutton(form, label, variable)

        spin_row = tk.Frame(form, bg=BASE)
        spin_row.pack(fill="x", pady=(6, 2))
        tk.Label(
            spin_row, text="Forecast days", font=ui_font(10), fg=SUBTEXT0,
            bg=BASE, width=18, anchor="w",
        ).pack(side="left")
        forecast_var = tk.StringVar(
            value=str(weather_cfg.get("forecast_days", 5))
        )
        tk.Spinbox(
            spin_row, from_=1, to=7, textvariable=forecast_var, width=5,
            bg=SURFACE0, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=SURFACE1,
            highlightcolor=BLUE, buttonbackground=SURFACE1,
            font=ui_font(10),
        ).pack(side="left")

        refresh_row = tk.Frame(form, bg=BASE)
        refresh_row.pack(fill="x", pady=(2, 2))
        tk.Label(
            refresh_row, text="Refresh every (minutes)", font=ui_font(10),
            fg=SUBTEXT0, bg=BASE, width=18, anchor="w",
        ).pack(side="left")
        refresh_var = tk.StringVar(
            value=str(weather_cfg.get("refresh_minutes", 15))
        )
        tk.Spinbox(
            refresh_row, from_=5, to=120, increment=5, textvariable=refresh_var,
            width=5, bg=SURFACE0, fg=TEXT, insertbackground=TEXT, relief="flat",
            bd=0, highlightthickness=1, highlightbackground=SURFACE1,
            highlightcolor=BLUE, buttonbackground=SURFACE1, font=ui_font(10),
        ).pack(side="left")

        section("Units")
        units_var = tk.StringVar(value=self.cfg.get("units", "metric"))
        units_row = tk.Frame(form, bg=BASE)
        units_row.pack(fill="x", pady=(2, 0))
        for value, label in (
            ("metric", "Celsius / km/h"),
            ("imperial", "Fahrenheit / mph"),
        ):
            tk.Radiobutton(
                units_row, text=label, variable=units_var, value=value,
                bg=BASE, fg=SUBTEXT0, activebackground=BASE, activeforeground=TEXT,
                selectcolor=SURFACE0, highlightthickness=0, bd=0,
                font=ui_font(10),
            ).pack(side="left", padx=(0, 14))

        # -- news topics -------------------------------------------------
        section(
            "News topics",
            f"Add up to {MAX_TOPICS} topics. Only headlines from the last 24 hours are shown.",
        )
        topics_frame = tk.Frame(form, bg=BASE)
        topics_frame.pack(fill="x")
        topic_rows: list[dict[str, Any]] = []

        def renumber_topics() -> None:
            for index, item in enumerate(topic_rows):
                item["label"].configure(text=f"{index + 1}.")

        def remove_topic_row(variable: tk.StringVar) -> None:
            for item in list(topic_rows):
                if item["var"] is variable:
                    item["row"].destroy()
                    topic_rows.remove(item)
                    break
            if not topic_rows:
                add_topic_row()
            renumber_topics()

        def add_topic_row(value: str = "") -> None:
            if len(topic_rows) >= MAX_TOPICS:
                return
            variable = tk.StringVar(value=value)
            row = tk.Frame(topics_frame, bg=BASE)
            row.pack(fill="x", pady=2)
            label = tk.Label(
                row, text="", font=ui_font(10), fg=OVERLAY1, bg=BASE,
                width=2, anchor="w",
            )
            label.pack(side="left")
            entry = self._entry(row, variable)
            entry.pack(side="left", fill="x", expand=True)
            PillButton(
                row, "Remove", command=lambda v=variable: remove_topic_row(v),
                bg=SURFACE1, hover=SURFACE2, padx=8, pady=2, font=ui_font(8),
            ).pack(side="right", padx=(6, 0))
            topic_rows.append({"row": row, "var": variable, "label": label})
            renumber_topics()
            scroll.bind_wheel()

        for topic in self.cfg["topics"]:
            add_topic_row(topic)
        PillButton(
            form, "Add topic", command=lambda: add_topic_row(), padx=10, pady=4,
            font=ui_font(9),
        ).pack(anchor="w", pady=(5, 0))

        # -- pinned shortcuts -------------------------------------------
        section("Pinned shortcuts", "Choose which shortcuts appear on the hub.")
        pins_frame = tk.Frame(form, bg=BASE)
        pins_frame.pack(fill="x")
        pin_vars: dict[str, tk.BooleanVar] = {}
        for index, (key, app) in enumerate(self.apps.items()):
            variable = tk.BooleanVar(value=key in self.cfg["pinned"])
            pin_vars[key] = variable
            tk.Checkbutton(
                pins_frame, text=app["name"], variable=variable,
                bg=BASE, fg=SUBTEXT0, activebackground=BASE,
                activeforeground=TEXT, selectcolor=SURFACE0,
                highlightthickness=0, bd=0, font=ui_font(10), anchor="w",
            ).grid(
                row=index // 3, column=index % 3, sticky="w",
                padx=(0, 16), pady=3,
            )

        # -- custom shortcuts -------------------------------------------
        section(
            "Custom shortcuts",
            "Add any application by name and command. New shortcuts are pinned automatically.",
        )
        custom_state: list[dict[str, Any]] = [
            dict(app) for app in self.cfg.get("custom_apps") or []
        ]
        custom_list = tk.Frame(form, bg=BASE)
        custom_list.pack(fill="x")

        def remove_custom(item: dict[str, Any]) -> None:
            if item in custom_state:
                custom_state.remove(item)
            render_custom()

        def render_custom() -> None:
            for child in custom_list.winfo_children():
                child.destroy()
            if not custom_state:
                tk.Label(
                    custom_list, text="No custom shortcuts yet.",
                    font=ui_font(9), fg=OVERLAY1, bg=BASE, anchor="w",
                ).pack(fill="x", pady=2)
                scroll.bind_wheel()
                return
            for item in custom_state:
                row = tk.Frame(custom_list, bg=SURFACE0)
                row.pack(fill="x", pady=2)
                info = tk.Frame(row, bg=SURFACE0)
                info.pack(side="left", fill="x", expand=True, padx=8, pady=4)
                tk.Label(
                    info, text=item.get("name", ""), font=ui_font(9, "bold"),
                    fg=TEXT, bg=SURFACE0, anchor="w",
                ).pack(fill="x")
                command = " ".join(item.get("launch") or [])
                if len(command) > 70:
                    command = command[:69] + "\u2026"
                tk.Label(
                    info, text=command, font=ui_font(8), fg=OVERLAY1,
                    bg=SURFACE0, anchor="w",
                ).pack(fill="x")
                PillButton(
                    row, "Remove", command=lambda entry=item: remove_custom(entry),
                    bg=SURFACE1, hover=SURFACE2, padx=8, pady=2,
                    font=ui_font(8),
                ).pack(side="right", padx=6)
            scroll.bind_wheel()

        render_custom()

        fields = tk.Frame(form, bg=BASE)
        fields.pack(fill="x", pady=(6, 0))
        name_var = tk.StringVar()
        command_var = tk.StringVar()
        icon_var = tk.StringVar()
        terminal_var = tk.BooleanVar(value=False)

        def field(label: str, variable: tk.StringVar) -> tk.Entry:
            row = tk.Frame(fields, bg=BASE)
            row.pack(fill="x", pady=2)
            tk.Label(
                row, text=label, font=ui_font(10), fg=SUBTEXT0, bg=BASE,
                width=10, anchor="w",
            ).pack(side="left")
            entry = self._entry(row, variable)
            entry.pack(side="left", fill="x", expand=True)
            return entry

        field("Name", name_var)
        field("Command", command_var)
        field("Icon", icon_var)

        command_help = tk.Frame(fields, bg=BASE)
        command_help.pack(fill="x", pady=(2, 0))
        tk.Label(
            command_help,
            text="Command may include arguments, e.g. firefox --new-window",
            font=ui_font(8), fg=OVERLAY1, bg=BASE, anchor="w",
        ).pack(side="left")
        PillButton(
            command_help, "Choose app\u2026", command=lambda: choose_app(),
            bg=SURFACE1, hover=SURFACE2, padx=8, pady=2, font=ui_font(8),
        ).pack(side="right")
        checkbutton(fields, "Run in a terminal", terminal_var)

        def choose_app() -> None:
            path = filedialog.askopenfilename(
                parent=window, title="Choose an application",
                initialdir="/usr/bin",
            )
            if not path:
                return
            if not name_var.get().strip():
                name_var.set(Path(path).name)
            command_var.set(path)

        def add_custom() -> None:
            name = name_var.get().strip()
            try:
                command = shlex.split(command_var.get().strip())
            except ValueError as error:
                messagebox.showerror(
                    "Home Hub", f"Could not parse the command:\n{error}",
                    parent=window,
                )
                return
            if not name or not command:
                messagebox.showerror(
                    "Home Hub", "Enter a name and a command.", parent=window
                )
                return
            taken = {key for key in self.apps}
            taken.update(str(item.get("key")) for item in custom_state)
            key = f"custom-{_slugify(name)}"
            if key in taken:
                base = key
                suffix = 2
                while f"{base}-{suffix}" in taken:
                    suffix += 1
                key = f"{base}-{suffix}"
            custom_state.append(
                {
                    "key": key,
                    "name": name,
                    "launch": command,
                    "icon": icon_var.get().strip() or None,
                    "monogram": name[:2].upper(),
                    "color": "BLUE",
                    "terminal": terminal_var.get(),
                }
            )
            name_var.set("")
            command_var.set("")
            icon_var.set("")
            terminal_var.set(False)
            render_custom()

        PillButton(
            form, "Add shortcut", command=add_custom, bg=BLUE, hover=LAVENDER,
            fg=CRUST, padx=12, pady=5, font=ui_font(9),
        ).pack(anchor="w", pady=(7, 10))

        # -- footer ------------------------------------------------------
        scroll.bind_wheel()
        tk.Frame(container, bg=SURFACE1, height=1).pack(fill="x", pady=(8, 10))
        buttons = tk.Frame(container, bg=BASE)
        buttons.pack(fill="x")

        def save() -> None:
            topics = [
                item["var"].get().strip()
                for item in topic_rows
                if item["var"].get().strip()
            ]
            problem = validate_topics(topics)
            if problem:
                messagebox.showerror("Home Hub", problem, parent=window)
                return
            city = city_var.get().strip()
            if mode_var.get() == "manual" and not city:
                messagebox.showerror(
                    "Home Hub", "Enter a city, or switch to auto-detect.",
                    parent=window,
                )
                return

            old_custom_keys = {
                app.get("key")
                for app in self.cfg.get("custom_apps") or []
                if isinstance(app, dict)
            }
            self.cfg["topics"] = topics
            self.cfg["units"] = units_var.get()
            self.cfg["theme"] = theme_key_by_label.get(
                theme_var.get(), self.cfg.get("theme", "mocha")
            )
            self.cfg["weather"] = {
                "forecast_days": _clamp_int(forecast_var.get(), 5, 1, 7),
                "refresh_minutes": _clamp_int(refresh_var.get(), 15, 5, 120),
                "show_details": weather_vars["show_details"].get(),
                "show_hourly": weather_vars["show_hourly"].get(),
                "show_forecast": weather_vars["show_forecast"].get(),
                "show_sun": weather_vars["show_sun"].get(),
            }
            self.cfg["location"] = {
                "mode": mode_var.get(),
                "city": city,
                "latitude": None,
                "longitude": None,
                "label": "",
            }
            self.cfg["custom_apps"] = [dict(item) for item in custom_state]

            pinned = [
                key for key in self.apps
                if pin_vars.get(key) is not None and pin_vars[key].get()
            ]
            for item in custom_state:
                key = item.get("key")
                if key and key not in old_custom_keys and key not in pinned:
                    pinned.append(key)
            self.cfg["pinned"] = pinned

            self.cfg = normalize_config(self.cfg)
            save_config(self.cfg)
            window.destroy()
            self._rebuild_ui()
            self._schedule_periodic_refresh()

        PillButton(
            buttons, "Cancel", command=window.destroy, bg=SURFACE1, hover=SURFACE2
        ).pack(side="right", padx=(8, 0))
        PillButton(buttons, "Save", command=save, bg=BLUE, hover=LAVENDER, fg=CRUST).pack(
            side="right"
        )

    def _entry(self, master: tk.Misc, variable: tk.StringVar) -> tk.Entry:
        return tk.Entry(
            master, textvariable=variable, font=ui_font(10), bg=SURFACE0, fg=TEXT,
            insertbackground=TEXT, relief="flat", bd=0, highlightthickness=1,
            highlightbackground=SURFACE1, highlightcolor=BLUE,
        )

    # -- window ---------------------------------------------------------

    def _toggle_fullscreen(self, _event: tk.Event | None = None) -> None:
        current = bool(self.root.attributes("-fullscreen"))
        self.root.attributes("-fullscreen", not current)

    def _leave_fullscreen(self, _event: tk.Event | None = None) -> None:
        try:
            self.root.attributes("-fullscreen", False)
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run_gui() -> int:
    cfg = load_config()
    apply_theme(cfg.get("theme", "mocha"))
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"Home Hub needs a graphical display: {error}", file=sys.stderr)
        return 1
    HubApp(root, cfg)
    root.mainloop()
    return 0


def cli_check(cfg: dict[str, Any]) -> int:
    failures = 0
    print(f"Topics: {', '.join(cfg['topics'])}")
    print(f"Location mode: {cfg['location'].get('mode', 'auto')}")
    print()

    try:
        weather = get_weather(cfg, load_cache().get("location"))
        print(
            f"Weather: {weather['temperature']}{weather['unit']} "
            f"{weather['description']} \u2014 {weather['city']}"
        )
        print(
            f"         feels {weather['feels']}\u00b0, humidity {weather['humidity']}%, "
            f"wind {weather['wind']} {weather['wind_unit']}, "
            f"high/low {weather['high']}\u00b0/{weather['low']}\u00b0"
        )
    except Exception as error:
        failures += 1
        print(f"Weather error: {error}")

    print()
    for topic in cfg["topics"]:
        try:
            article = fetch_news_article(topic)
            if article is None:
                print(f"[{topic}] no articles in the last 24 hours")
            else:
                print(
                    f"[{topic}] {article.title} "
                    f"({article.source or 'unknown source'}, {relative_time(article.published)})"
                )
        except Exception as error:
            failures += 1
            print(f"[{topic}] error: {error}")

    print()
    print("Result:", "all sources reachable" if not failures else f"{failures} failure(s)")
    return 0 if failures < 1 + len(cfg["topics"]) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Home Hub desktop dashboard")
    parser.add_argument(
        "--check", action="store_true",
        help="fetch weather and news, print a report, and exit",
    )
    args = parser.parse_args(argv)
    cfg = load_config()
    if args.check:
        return cli_check(cfg)
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
