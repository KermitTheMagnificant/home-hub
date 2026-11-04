import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hub  # noqa: E402


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example</title>
    <item>
      <title>Fresh headline - Example News</title>
      <link>https://example.com/fresh</link>
      <pubDate>Mon, 02 Nov 2026 11:30:00 GMT</pubDate>
      <source>Example News</source>
    </item>
    <item>
      <title>Older headline - Example News</title>
      <link>https://example.com/older</link>
      <pubDate>Sat, 31 Oct 2026 11:30:00 GMT</pubDate>
      <source>Example News</source>
    </item>
    <item>
      <title>Second recent - The Wire</title>
      <link>https://example.com/second</link>
      <pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate>
      <source>The Wire</source>
    </item>
    <item>
      <title>No date</title>
      <link>https://example.com/nodate</link>
    </item>
  </channel>
</rss>
"""

WEATHER = {
    "current": {
        "temperature_2m": 12.4,
        "relative_humidity_2m": 63,
        "apparent_temperature": 10.9,
        "is_day": 1,
        "weather_code": 3,
        "wind_speed_10m": 8.2,
    },
    "daily": {
        "time": ["2026-11-02", "2026-11-03", "2026-11-04"],
        "weather_code": [3, 61, 0],
        "temperature_2m_max": [14.2, 13.0, 16.7],
        "temperature_2m_min": [7.1, 6.0, 8.0],
        "sunrise": [
            "2026-11-02T07:12",
            "2026-11-03T07:13",
            "2026-11-04T07:15",
        ],
        "sunset": [
            "2026-11-02T17:03",
            "2026-11-03T17:01",
            "2026-11-04T17:00",
        ],
    },
}


class RelativeTimeTests(unittest.TestCase):
    def test_relative_time_buckets(self):
        now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(hub.relative_time(now, now), "just now")
        self.assertEqual(
            hub.relative_time(datetime(2026, 11, 2, 11, 30, tzinfo=timezone.utc), now),
            "30m ago",
        )
        self.assertEqual(
            hub.relative_time(datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc), now),
            "3h ago",
        )
        self.assertEqual(
            hub.relative_time(datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc), now),
            "1d ago",
        )

    def test_greeting(self):
        self.assertEqual(hub.greeting_for(3), "Good night")
        self.assertEqual(hub.greeting_for(8), "Good morning")
        self.assertEqual(hub.greeting_for(14), "Good afternoon")
        self.assertEqual(hub.greeting_for(21), "Good evening")


class NewsTests(unittest.TestCase):
    def test_only_articles_from_last_24_hours(self):
        now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        articles = hub.parse_news(RSS, "Technology", now=now)
        self.assertEqual([a.title for a in articles], [
            "Fresh headline",
            "Second recent",
        ])
        self.assertEqual(articles[0].source, "Example News")
        self.assertTrue(articles[0].published <= now)

    def test_parse_news_sorted_newest_first(self):
        now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        articles = hub.parse_news(RSS, "Tech", now=now)
        self.assertGreaterEqual(articles[0].published, articles[1].published)

    def test_bad_xml_raises(self):
        with self.assertRaises(Exception):
            hub.parse_news("not xml", "Tech")


class CacheTests(unittest.TestCase):
    def test_article_roundtrip(self):
        article = hub.Article(
            "Science",
            "A headline",
            "https://example.com/x",
            "Source",
            datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc),
        )
        restored = hub.article_from_cache(article.to_cache())
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.title, article.title)
        self.assertEqual(restored.link, article.link)
        self.assertEqual(restored.published, article.published)

    def test_bad_cache_entry(self):
        self.assertIsNone(hub.article_from_cache({"title": "x"}))
        self.assertIsNone(hub.article_from_cache({}))


class ConfigTests(unittest.TestCase):
    def test_normalize_keeps_custom_topic_count_and_dedupes(self):
        cfg = hub.normalize_config(
            {"topics": ["Tech", "tech", "Science"], "pinned": ["spotify", "bogus", "github"]}
        )
        self.assertEqual(cfg["topics"], ["Tech", "Science"])
        self.assertEqual(cfg["pinned"], ["spotify", "github"])

    def test_normalize_missing_keys(self):
        cfg = hub.normalize_config({})
        self.assertEqual(cfg["topics"], hub.DEFAULT_TOPICS)
        self.assertEqual(cfg["pinned"], list(hub.APPS))
        self.assertEqual(cfg["units"], "metric")
        self.assertEqual(cfg["theme"], "mocha")
        self.assertEqual(cfg["weather"]["forecast_days"], 5)
        self.assertEqual(cfg["location"]["mode"], "auto")

    def test_validate_topics(self):
        self.assertIsNone(hub.validate_topics(["A", "B", "C", "D", "E"]))
        self.assertIsNone(hub.validate_topics(["A", "B", "C", "D", ""]))
        self.assertIsNotNone(hub.validate_topics([]))
        self.assertIsNotNone(hub.validate_topics(["A", "B", "C", "D", "a"]))
        self.assertIsNotNone(
            hub.validate_topics([f"Topic {index}" for index in range(hub.MAX_TOPICS + 1)])
        )

    def test_roundtrip(self):
        cfg = hub.normalize_config({"units": "imperial"})
        self.assertEqual(cfg["units"], "imperial")
        json.dumps(cfg)

    def test_custom_apps_and_pins(self):
        cfg = hub.normalize_config(
            {
                "custom_apps": [
                    {"name": "Firefox", "command": "firefox --new-window"},
                    {"name": "Ignored", "command": ""},
                ],
                "pinned": ["spotify", "custom-firefox"],
            }
        )
        self.assertEqual(len(cfg["custom_apps"]), 1)
        custom = cfg["custom_apps"][0]
        self.assertEqual(custom["key"], "custom-firefox")
        self.assertEqual(custom["launch"], ["firefox", "--new-window"])
        self.assertIn("custom-firefox", cfg["pinned"])
        registry = hub.build_app_registry(cfg)
        self.assertIn("custom-firefox", registry)
        self.assertEqual(
            hub.build_launch_command("custom-firefox", registry)[0],
            hub.find_executable("firefox") or "firefox",
        )

    def test_weather_options_are_clamped(self):
        cfg = hub.normalize_config(
            {"weather": {"forecast_days": 99, "refresh_minutes": 1}}
        )
        self.assertEqual(cfg["weather"]["forecast_days"], 7)
        self.assertEqual(cfg["weather"]["refresh_minutes"], 5)


class ThemeTests(unittest.TestCase):
    def test_theme_switches_palette(self):
        try:
            mocha_base = hub.BASE
            hub.apply_theme("latte")
            self.assertNotEqual(hub.BASE, mocha_base)
            self.assertEqual(hub.THEME, "latte")
            self.assertEqual(len(hub.TOPIC_COLORS), 8)
            self.assertEqual(hub.resolve_color("BLUE"), hub.THEMES["latte"]["BLUE"])
        finally:
            hub.apply_theme("mocha")


class RecentFolderTests(unittest.TestCase):
    def test_parse_xbel_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Project"
            folder.mkdir()
            xbel = f"""<?xml version="1.0" encoding="UTF-8"?>
<xbel version="1.0" xmlns:mime="http://www.freedesktop.org/standards/shared-mime-info">
  <bookmark href="{folder.as_uri()}" added="2026-11-02T10:00:00Z">
    <info><metadata><mime:mime-type type="inode/directory"/></metadata></info>
  </bookmark>
  <bookmark href="file:///does/not/exist" added="2026-11-02T11:00:00Z"/>
</xbel>"""
            folders = hub.parse_xbel_folders(xbel)
            self.assertEqual(len(folders), 1)
            self.assertEqual(folders[0]["path"], str(folder))
            self.assertEqual(folders[0]["name"], "Project")

    def test_cache_history_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            Path, "home", return_value=Path(tmp)
        ):
            cache = {}
            hub.record_recent_folder(cache, tmp)
            folders = hub.recent_folders(cache)
            self.assertEqual(folders[0]["path"], str(Path(tmp)))
            hub.forget_recent_folder(cache, tmp)
            self.assertEqual(cache["recent_folders"], [])


class WeatherTests(unittest.TestCase):
    def test_weather_codes(self):
        description, glyph, _ = hub.weather_info(0)
        self.assertEqual(description, "Clear sky")
        self.assertTrue(glyph)
        self.assertEqual(hub.weather_info(9999)[0], "Unknown conditions")

    @mock.patch("hub.http_get")
    def test_geocode(self, fake_get):
        fake_get.return_value = json.dumps(
            {
                "results": [
                    {
                        "name": "Paris",
                        "latitude": 48.85,
                        "longitude": 2.35,
                        "country_code": "FR",
                    }
                ]
            }
        )
        location = hub.geocode("Paris")
        self.assertEqual(location["label"], "Paris, FR")
        self.assertAlmostEqual(location["latitude"], 48.85)

    @mock.patch("hub.http_get")
    def test_geocode_missing(self, fake_get):
        fake_get.return_value = json.dumps({"results": []})
        with self.assertRaises(RuntimeError):
            hub.geocode("Nowhere")

    @mock.patch("hub.resolve_location")
    @mock.patch("hub.http_get")
    def test_get_weather_parses_payload(self, fake_get, fake_location):
        fake_location.return_value = {
            "latitude": 1.0,
            "longitude": 2.0,
            "label": "Testville, TS",
        }
        fake_get.return_value = json.dumps(WEATHER)
        cfg = hub.normalize_config({"units": "metric"})
        weather = hub.get_weather(cfg)
        self.assertEqual(weather["city"], "Testville, TS")
        self.assertEqual(weather["temperature"], 12)
        self.assertEqual(weather["feels"], 11)
        self.assertEqual(weather["high"], 14)
        self.assertEqual(weather["low"], 7)
        self.assertEqual(weather["unit"], "\u00b0C")
        self.assertEqual(weather["sunrise"], "07:12")
        self.assertEqual(len(weather["daily"]), 3)
        self.assertEqual(weather["location"]["label"], "Testville, TS")

    @mock.patch("hub.detect_ip_location")
    def test_resolve_manual_location(self, fake_detect):
        cfg = hub.normalize_config(
            {"location": {"mode": "manual", "city": "Berlin"}}
        )
        with mock.patch("hub.geocode", return_value={"label": "Berlin, DE"}) as fake:
            location = hub.resolve_location(cfg)
        fake.assert_called_once_with("Berlin")
        self.assertEqual(location["label"], "Berlin, DE")
        fake_detect.assert_not_called()


class LauncherTests(unittest.TestCase):
    def test_known_apps(self):
        self.assertEqual(
            set(hub.APPS),
            {"spotify", "opencode", "ollama", "hermes", "vscode", "github"},
        )

    def test_launch_command_is_list(self):
        command = hub.build_launch_command("spotify")
        self.assertIsInstance(command, list)
        self.assertTrue(command)


if __name__ == "__main__":
    unittest.main()
