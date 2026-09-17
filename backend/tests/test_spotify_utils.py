import unittest

from spotify_utils import (
    extract_added_dates,
    generate_month_range,
    get_playlist_tracks,
)


class SpotifyUtilsTest(unittest.TestCase):
    def test_playlist_fetch_errors_are_not_disguised_as_empty_playlists(self):
        class BrokenSpotify:
            def playlist_tracks(self, playlist_id):
                raise RuntimeError("Spotify is unavailable")

        with self.assertRaisesRegex(RuntimeError, "Spotify is unavailable"):
            get_playlist_tracks(BrokenSpotify(), "playlist")

    def test_extract_added_dates_skips_only_malformed_items(self):
        self.assertEqual(
            extract_added_dates(
                [
                    {"added_at": "2024-01-02T00:00:00Z"},
                    {"added_at": None},
                    {},
                    None,
                    {"added_at": "2024-03-04T00:00:00Z"},
                ]
            ),
            ["2024-01-02", "2024-03-04"],
        )

    def test_generate_month_range_includes_bounds(self):
        self.assertEqual(
            generate_month_range("2023-11", "2024-02"),
            ["2023-11", "2023-12", "2024-01", "2024-02"],
        )


if __name__ == "__main__":
    unittest.main()
