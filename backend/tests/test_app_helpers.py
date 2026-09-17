import unittest
from datetime import date
from unittest.mock import Mock, patch

import app as app_module
from app import (
    aggregate_added_dates,
    app,
    build_analysis_response,
    build_insights_response,
    build_playlist_insight,
    build_wrapped_response,
    get_cached_added_dates,
    get_current_user_playlists,
    normalize_playlist,
    normalize_playlist_ids,
)


class FakeSpotify:
    def __init__(self):
        self.pages = [
            {
                "items": [
                    {
                        "id": "one",
                        "name": "First",
                        "owner": {"display_name": "Owner One"},
                        "images": [{"url": "https://example.com/one.jpg"}],
                        "tracks": {"total": 10},
                        "public": False,
                        "collaborative": True,
                    }
                ],
                "next": "next-page",
            },
            {
                "items": [
                    {
                        "id": "two",
                        "name": "Second",
                        "owner": {"id": "owner-two"},
                        "images": [],
                        "tracks": {"total": 3},
                        "public": True,
                        "collaborative": False,
                    }
                ],
                "next": None,
            },
        ]
        self.index = 0

    def current_user_playlists(self, limit=50):
        return self.pages[0]

    def next(self, results):
        self.index += 1
        return self.pages[self.index]


class AppHelperTest(unittest.TestCase):
    def test_normalize_playlist_handles_missing_optional_fields(self):
        self.assertEqual(
            normalize_playlist({"id": "abc", "name": None}),
            {
                "id": "abc",
                "name": "Untitled playlist",
                "ownerName": "Unknown owner",
                "imageUrl": None,
                "trackCount": 0,
                "public": None,
                "collaborative": False,
            },
        )

    def test_get_current_user_playlists_paginates_and_normalizes(self):
        playlists = get_current_user_playlists(FakeSpotify())

        self.assertEqual(len(playlists), 2)
        self.assertEqual(playlists[0]["name"], "First")
        self.assertEqual(playlists[0]["ownerName"], "Owner One")
        self.assertEqual(playlists[0]["imageUrl"], "https://example.com/one.jpg")
        self.assertEqual(playlists[1]["ownerName"], "owner-two")
        self.assertIsNone(playlists[1]["imageUrl"])

    def test_normalize_playlist_ids_supports_new_and_legacy_payloads(self):
        self.assertEqual(
            normalize_playlist_ids({"playlistIds": ["a", "", 4, "b", "a", "bad id"]}),
            ["a", "b"],
        )
        self.assertEqual(normalize_playlist_ids({"playlistId": "legacy"}), ["legacy"])

    def test_get_cached_added_dates_fetches_playlist_tracks_once(self):
        app_module.added_dates_cache = {}
        app_module.playlist_tracks_cache = {}
        sp = Mock()

        with patch(
            "app.get_playlist_tracks", return_value=[{"added_at": "2024-01-02T00:00:00Z"}]
        ) as fetch_tracks:
            self.assertEqual(get_cached_added_dates(sp, "playlist-a"), ["2024-01-02"])
            self.assertEqual(get_cached_added_dates(sp, "playlist-a"), ["2024-01-02"])

        fetch_tracks.assert_called_once_with(sp, "playlist-a")

    def test_build_wrapped_response_matches_top_tracks_and_artists(self):
        short_track = {
            "id": "track-one",
            "name": "Current Song",
            "artists": [{"id": "artist-one", "name": "Artist One"}],
            "album": {"name": "Album One", "images": [{"url": "https://example.com/album.jpg"}]},
        }
        long_track = {
            "id": "track-two",
            "name": "Long Song",
            "artists": [{"id": "artist-two", "name": "Artist Two"}],
            "album": {"name": "Album Two", "images": []},
        }
        response = build_wrapped_response(
            [{"id": "playlist-one", "name": "Playlist One"}],
            {
                "playlist-one": [
                    {"track": short_track},
                    {"track": long_track},
                    {
                        "track": {
                            "id": "track-three",
                            "name": "Deep Cut",
                            "artists": [{"id": "artist-one", "name": "Artist One"}],
                            "album": {"name": "Album Three", "images": []},
                        }
                    },
                ]
            },
            {
                "short_term": [short_track],
                "long_term": [long_track],
            },
            {
                "short_term": [{"id": "artist-one", "name": "Artist One", "images": []}],
                "long_term": [{"id": "artist-two", "name": "Artist Two", "images": []}],
            },
        )

        wrapped = response["playlists"][0]
        self.assertEqual(wrapped["tasteMatch"]["shortTermMatched"], 1)
        self.assertEqual(wrapped["tasteMatch"]["longTermMatched"], 1)
        self.assertEqual(wrapped["currentFavorites"][0]["name"], "Current Song")
        self.assertEqual(wrapped["allTimeFavorites"][0]["name"], "Long Song")
        self.assertEqual(wrapped["artistGravity"][0]["name"], "Artist One")
        self.assertEqual(wrapped["artistGravity"][0]["playlistTrackCount"], 2)

    def test_sum_response_aligns_labels_and_adds_counts(self):
        response = build_analysis_response(
            [
                {"playlistId": "a", "label": "A", "labels": ["2024-01", "2024-03"], "data": [2, 4]},
                {"playlistId": "b", "label": "B", "labels": ["2024-02", "2024-03"], "data": [3, 1]},
            ],
            "month",
            "sum",
        )

        self.assertEqual(response["labels"], ["2024-01", "2024-02", "2024-03"])
        self.assertEqual(response["data"], [2, 3, 5])
        self.assertEqual(response["datasets"][0]["data"], [2, 3, 5])

    def test_compare_response_aligns_labels_and_fills_zeroes(self):
        response = build_analysis_response(
            [
                {"playlistId": "a", "label": "A", "labels": ["2024-01"], "data": [2]},
                {"playlistId": "b", "label": "B", "labels": ["2024-02"], "data": [3]},
            ],
            "month",
            "compare",
        )

        self.assertEqual(response["labels"], ["2024-01", "2024-02"])
        self.assertEqual(response["datasets"][0]["data"], [2, 0])
        self.assertEqual(response["datasets"][1]["data"], [0, 3])

    def test_season_aggregation_accepts_month_start(self):
        labels, data = aggregate_added_dates(
            ["2022-08-01", "2022-09-01", "2022-10-01"],
            "season",
            "2022-08",
        )

        self.assertEqual(labels, ["Summer 2022", "Fall 2022"])
        self.assertEqual(data, [1, 2])

    def test_build_playlist_insight_calculates_activity_stats(self):
        insight = build_playlist_insight(
            {"id": "a", "name": "A"},
            [
                "2024-01-01",
                "2024-01-10",
                "2024-03-15",
                "2024-03-16",
                "2024-06-01",
            ],
            today=date(2024, 7, 1),
        )

        self.assertEqual(insight["totalTracks"], 5)
        self.assertEqual(insight["firstAddDate"], "2024-01-01")
        self.assertEqual(insight["lastAddDate"], "2024-06-01")
        self.assertEqual(insight["daysSinceLastAdd"], 30)
        self.assertEqual(insight["addsLast90Days"], 1)
        self.assertEqual(insight["addsPrevious90Days"], 3)
        self.assertEqual(insight["momentumDelta"], -2)
        self.assertEqual(insight["biggestSpike"], {"label": "2024-01", "count": 2})
        self.assertEqual(insight["longestDroughtDays"], 77)
        self.assertIn("monthlyTrend", insight)

    def test_build_playlist_insight_detects_early_spike_shape(self):
        insight = build_playlist_insight(
            {"id": "fade", "name": "Fade"},
            [
                "2023-01-01",
                "2023-01-02",
                "2023-02-01",
                "2023-02-02",
                "2023-03-01",
                "2023-03-02",
                "2023-06-01",
            ],
            today=date(2023, 7, 1),
        )

        self.assertEqual(insight["monthlyTrend"]["longTermDirection"], "Decreasing")
        self.assertEqual(insight["monthlyTrend"]["shape"], "Early spike")
        self.assertGreater(insight["monthlyTrend"]["falloffScore"], 0)
        self.assertGreater(insight["monthlyTrend"]["launchShare"], 0.5)

    def test_build_playlist_insight_detects_long_term_decrease_despite_recent_add(self):
        insight = build_playlist_insight(
            {"id": "down", "name": "Down"},
            [
                *["2023-08-01"] * 78,
                *["2023-09-01"] * 35,
                *["2023-10-01"] * 30,
                *["2024-01-01"] * 24,
                *["2024-04-01"] * 18,
                *["2024-08-01"] * 14,
                *["2025-02-01"] * 9,
                *["2025-08-01"] * 7,
                *["2026-04-01"] * 3,
                "2026-06-26",
            ],
            today=date(2026, 6, 27),
        )

        self.assertEqual(insight["monthlyTrend"]["longTermDirection"], "Decreasing")
        self.assertEqual(insight["monthlyTrend"]["recentActivity"], "Quiet recently")

    def test_build_insights_response_returns_rankings(self):
        insights = [
            {
                "playlistId": "a",
                "name": "A",
                "totalTracks": 10,
                "addsLast90Days": 2,
                "addsPrevious90Days": 1,
                "momentumDelta": 1,
                "firstAddDate": "2024-01-01",
                "lastAddDate": "2024-05-01",
                "daysSinceLastAdd": 10,
                "biggestSpike": {"label": "2024-01", "count": 4},
                "longestDroughtDays": 30,
                "consistencyScore": 0.4,
            },
            {
                "playlistId": "b",
                "name": "B",
                "totalTracks": 20,
                "addsLast90Days": 9,
                "addsPrevious90Days": 2,
                "momentumDelta": 7,
                "firstAddDate": "2023-01-01",
                "lastAddDate": "2024-03-01",
                "daysSinceLastAdd": 70,
                "biggestSpike": {"label": "2024-02", "count": 8},
                "longestDroughtDays": 90,
                "consistencyScore": 0.7,
            },
        ]

        response = build_insights_response(
            [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            insights,
        )

        self.assertEqual(response["summary"]["playlistCount"], 2)
        self.assertEqual(response["summary"]["totalTracks"], 30)
        self.assertEqual(response["summary"]["momentumDelta"], 8)
        self.assertEqual(response["rankings"]["biggestRecentMomentum"]["name"], "B")
        self.assertEqual(response["rankings"]["mostRecentlyActive"]["name"], "A")
        self.assertEqual(response["rankings"]["mostDormant"]["name"], "B")
        self.assertIn("biggestFalloff", response["rankings"])

    def test_api_routes_are_not_captured_by_static_proxy(self):
        with app.test_client() as client:
            response = client.get("/api/session")

        self.assertEqual(response.status_code, 200)
        self.assertIn("authenticated", response.get_json())


if __name__ == "__main__":
    unittest.main()
