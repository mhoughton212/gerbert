import logging
import math
import os
import re
import secrets
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import spotipy
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory
from spotify_utils import (
    aggregate_by_season,
    extract_added_dates,
    generate_month_range,
    get_playlist_tracks,
    month_to_season,
    sort_seasons,
)
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")

STATIC_DIR = PROJECT_ROOT / "frontend" / "build"
TOKEN_CACHE_PATH = os.getenv("SPOTIFY_CACHE_PATH", str(BASE_DIR / ".cache"))

app = Flask(__name__, static_folder=str(STATIC_DIR))
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
token_info = None
playlist_cache = None
playlist_tracks_cache = {}
added_dates_cache = {}
top_items_cache = {}
sp_oauth = None
oauth_state = None

SPOTIFY_SCOPE = "playlist-read-private playlist-read-collaborative user-top-read"
TOP_ITEM_LIMIT = 50
MAX_SELECTED_PLAYLISTS = 50
PLAYLIST_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{1,100}$")


def get_spotify_oauth():
    global sp_oauth

    if sp_oauth is None:
        config = {
            "client_id": os.getenv("SPOTIPY_CLIENT_ID"),
            "client_secret": os.getenv("SPOTIPY_CLIENT_SECRET"),
            "redirect_uri": os.getenv("SPOTIPY_REDIRECT_URI"),
        }
        missing = [name for name, value in config.items() if not value]
        if missing:
            raise RuntimeError(
                "Spotify OAuth is not configured. Copy backend/.env.example to backend/.env."
            )

        sp_oauth = SpotifyOAuth(
            **config,
            scope=SPOTIFY_SCOPE,
            cache_path=TOKEN_CACHE_PATH,
        )

    return sp_oauth


def get_token():
    global token_info
    try:
        oauth = get_spotify_oauth()
        token_info = oauth.get_cached_token()

        if token_info and oauth.is_token_expired(token_info):
            token_info = oauth.refresh_access_token(token_info["refresh_token"])
    except RuntimeError:
        token_info = None
    except Exception:
        logging.exception("Unable to load or refresh the Spotify token")
        token_info = None

    if not token_info:
        return None

    return token_info


def require_token():
    active_token = get_token()

    if not active_token or "access_token" not in active_token:
        return None, (jsonify({"error": "Not authenticated"}), 401)

    return active_token, None


def spotify_client(active_token):
    return spotipy.Spotify(auth=active_token["access_token"])


def normalize_playlist(playlist):
    owner = playlist.get("owner") or {}
    tracks = playlist.get("tracks") or {}
    images = playlist.get("images") or []

    return {
        "id": playlist.get("id"),
        "name": playlist.get("name") or "Untitled playlist",
        "ownerName": owner.get("display_name") or owner.get("id") or "Unknown owner",
        "imageUrl": images[0].get("url") if images else None,
        "trackCount": tracks.get("total", 0),
        "public": playlist.get("public"),
        "collaborative": bool(playlist.get("collaborative")),
    }


def get_current_user_playlists(sp):
    results = sp.current_user_playlists(limit=50)
    playlists = results.get("items", [])

    while results.get("next"):
        results = sp.next(results)
        playlists.extend(results.get("items", []))

    return [normalize_playlist(playlist) for playlist in playlists if playlist.get("id")]


def get_cached_playlists(sp):
    global playlist_cache

    if playlist_cache is None:
        playlist_cache = get_current_user_playlists(sp)

    return playlist_cache


def get_cached_playlist_tracks(sp, playlist_id):
    if playlist_id not in playlist_tracks_cache:
        playlist_tracks_cache[playlist_id] = get_playlist_tracks(sp, playlist_id)

    return playlist_tracks_cache[playlist_id]


def get_cached_added_dates(sp, playlist_id):
    if playlist_id not in added_dates_cache:
        tracks = get_cached_playlist_tracks(sp, playlist_id)
        added_dates_cache[playlist_id] = extract_added_dates(tracks)

    return added_dates_cache[playlist_id]


def get_cached_top_items(sp, item_type, time_range):
    cache_key = (item_type, time_range)

    if cache_key not in top_items_cache:
        if item_type == "tracks":
            response = sp.current_user_top_tracks(
                limit=TOP_ITEM_LIMIT,
                offset=0,
                time_range=time_range,
            )
        elif item_type == "artists":
            response = sp.current_user_top_artists(
                limit=TOP_ITEM_LIMIT,
                offset=0,
                time_range=time_range,
            )
        else:
            raise ValueError("Invalid top item type")

        top_items_cache[cache_key] = response.get("items", [])

    return top_items_cache[cache_key]


def aggregate_by_month(added_dates, start):
    added_months = [date[:7] for date in added_dates]
    month_counts = Counter(added_months)
    sorted_months = sorted(month_counts.items())

    start_month = sorted_months[0][0] if start == "start" else start
    end_month = sorted_months[-1][0]
    labels = generate_month_range(start_month, end_month)

    return labels, [month_counts.get(month, 0) for month in labels]


def month_range_count(start_month, end_month):
    return len(generate_month_range(start_month, end_month))


def aggregate_added_dates(added_dates, view_mode, start):
    if view_mode == "season":
        if isinstance(start, str) and len(start) == 7 and start[4] == "-":
            year, month = start.split("-")
            start = month_to_season(year, month)
        return aggregate_by_season(added_dates, start)

    return aggregate_by_month(added_dates, start)


def sort_analysis_labels(labels, view_mode):
    sorted_labels = list(labels)

    if view_mode == "season":
        return sorted(sorted_labels, key=sort_seasons)

    return sorted(sorted_labels)


def normalize_playlist_ids(data):
    playlist_ids = data.get("playlistIds")

    if playlist_ids is None and data.get("playlistId"):
        playlist_ids = [data.get("playlistId")]

    if not isinstance(playlist_ids, list):
        return []

    normalized = []
    for playlist_id in playlist_ids:
        if (
            isinstance(playlist_id, str)
            and PLAYLIST_ID_PATTERN.fullmatch(playlist_id)
            and playlist_id not in normalized
        ):
            normalized.append(playlist_id)

    return normalized


def fetch_playlist_analysis(sp, playlist_id, playlist_name, view_mode, start):
    added_dates = get_cached_added_dates(sp, playlist_id)

    if not added_dates:
        return {
            "playlistId": playlist_id,
            "label": playlist_name,
            "labels": [],
            "data": [],
            "firstAddDate": None,
        }

    labels, data_points = aggregate_added_dates(added_dates, view_mode, start)

    return {
        "playlistId": playlist_id,
        "label": playlist_name,
        "labels": labels,
        "data": data_points,
        "firstAddDate": min(added_dates),
    }


def align_dataset(analysis, labels):
    counts = dict(zip(analysis["labels"], analysis["data"], strict=True))

    return {
        "label": analysis["label"],
        "playlistId": analysis["playlistId"],
        "data": [counts.get(label, 0) for label in labels],
    }


def build_analysis_response(analyses, view_mode, chart_mode):
    all_labels = {label for analysis in analyses for label in analysis["labels"]}
    labels = sort_analysis_labels(all_labels, view_mode)
    first_add_dates = [
        analysis["firstAddDate"] for analysis in analyses if analysis.get("firstAddDate")
    ]
    first_add_date = min(first_add_dates) if first_add_dates else None

    if chart_mode == "compare":
        return {
            "labels": labels,
            "datasets": [align_dataset(analysis, labels) for analysis in analyses],
            "meta": {"firstAddDate": first_add_date},
        }

    totals = [0 for _ in labels]
    label_indexes = {label: index for index, label in enumerate(labels)}

    for analysis in analyses:
        for label, value in zip(analysis["labels"], analysis["data"], strict=True):
            totals[label_indexes[label]] += value

    label = "Selected playlist total" if len(analyses) > 1 else analyses[0]["label"]

    return {
        "labels": labels,
        "data": totals,
        "datasets": [{"label": label, "data": totals}],
        "meta": {"firstAddDate": first_add_date},
    }


def parse_added_dates(added_dates):
    return sorted(datetime.strptime(date_str, "%Y-%m-%d").date() for date_str in added_dates)


def most_common_bucket(labels):
    if not labels:
        return None

    label, count = Counter(labels).most_common(1)[0]
    return {"label": label, "count": count}


def longest_gap_days(dates):
    if len(dates) < 2:
        return 0

    return max(
        (current - previous).days for previous, current in zip(dates, dates[1:], strict=False)
    )


def average(values):
    return round(sum(values) / len(values), 2) if values else 0


def linear_regression(values):
    if len(values) < 2:
        return {"slope": 0, "rSquared": 0}

    x_values = list(range(len(values)))
    y_values = [math.log1p(value) for value in values]
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    denominator = sum((value - x_mean) ** 2 for value in x_values)

    if denominator == 0:
        return {"slope": 0, "rSquared": 0}

    slope = (
        sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values, strict=True))
        / denominator
    )
    intercept = y_mean - slope * x_mean
    fitted_values = [intercept + slope * x for x in x_values]
    residual_sum = sum(
        (actual - fitted) ** 2 for actual, fitted in zip(y_values, fitted_values, strict=True)
    )
    total_sum = sum((actual - y_mean) ** 2 for actual in y_values)
    r_squared = 1 - residual_sum / total_sum if total_sum else 0

    return {"slope": round(slope, 4), "rSquared": round(max(0, r_squared), 2)}


def month_start(item):
    return date(item.year, item.month, 1)


def shift_month(item, offset):
    month_index = item.month - 1 + offset
    return date(item.year + month_index // 12, month_index % 12 + 1, 1)


def build_monthly_trend(dates, today=None):
    today = today or date.today()

    if len(dates) < 2:
        return {
            "label": "Not enough history",
            "longTermDirection": "Not enough history",
            "recentActivity": "Not enough history",
            "shape": "Not enough history",
            "firstHalfAverage": 0,
            "secondHalfAverage": 0,
            "delta": 0,
            "percentChange": None,
            "falloffScore": 0,
            "baselineAverage": 0,
            "recentAverage": 0,
            "previousAverage": 0,
            "launchAverage": 0,
            "launchShare": 0,
            "peakMonthShare": 0,
            "trendSlope": 0,
            "trendRSquared": 0,
        }

    month_counts = Counter(item.strftime("%Y-%m") for item in dates)
    end_month = max(month_start(dates[-1]), month_start(today))
    months = generate_month_range(dates[0].strftime("%Y-%m"), end_month.strftime("%Y-%m"))
    monthly_values = [month_counts.get(month, 0) for month in months]
    completed_end_month = shift_month(month_start(today), -1)
    direction_end_month = max(month_start(dates[0]), min(completed_end_month, end_month))
    direction_months = generate_month_range(
        dates[0].strftime("%Y-%m"), direction_end_month.strftime("%Y-%m")
    )
    direction_values = [month_counts.get(month, 0) for month in direction_months]
    total_adds = sum(monthly_values)
    baseline_average = average(monthly_values)
    recent_values = monthly_values[-3:]
    previous_values = monthly_values[-6:-3]
    launch_values = monthly_values[:3]
    direction_recent_values = direction_values[-3:]
    recent_average = average(recent_values)
    previous_average = average(previous_values)
    launch_average = average(launch_values)
    direction_recent_average = average(direction_recent_values)
    launch_share = round(sum(launch_values) / total_adds, 2) if total_adds else 0
    peak_month_share = round(max(monthly_values) / total_adds, 2) if total_adds else 0
    delta = round(recent_average - previous_average, 2)
    falloff_score = round(max(0, launch_average - recent_average), 2)
    percent_change = round((delta / previous_average) * 100, 1) if previous_average else None
    trend = linear_regression(direction_values)

    if len(monthly_values) < 4:
        return {
            "label": "Not enough history",
            "longTermDirection": "Not enough history",
            "recentActivity": "Not enough history",
            "shape": "Not enough history",
            "firstHalfAverage": launch_average,
            "secondHalfAverage": recent_average,
            "delta": 0,
            "percentChange": None,
            "falloffScore": 0,
            "baselineAverage": baseline_average,
            "recentAverage": recent_average,
            "previousAverage": previous_average,
            "launchAverage": launch_average,
            "launchShare": launch_share,
            "peakMonthShare": peak_month_share,
            "trendSlope": trend["slope"],
            "trendRSquared": trend["rSquared"],
        }

    current_drought_days = (today - dates[-1]).days
    slope = trend["slope"]
    direction_baseline = average(direction_values)
    has_recent_revival = previous_average <= max(
        0.5, baseline_average * 0.45
    ) and recent_average >= max(1, baseline_average * 1.15)
    is_spiky = peak_month_share >= 0.35 and max(monthly_values) >= 5
    has_early_spike = launch_share >= 0.45 and launch_average > max(
        1, direction_recent_average * 1.35
    )

    if len(direction_values) < 6:
        long_term_direction = "Not enough history"
    elif slope <= -0.035 and direction_recent_average <= max(
        direction_baseline * 0.9, launch_average * 0.8
    ):
        long_term_direction = "Decreasing"
    elif slope >= 0.035 and direction_recent_average >= max(
        direction_baseline * 1.1, launch_average * 0.85
    ):
        long_term_direction = "Increasing"
    elif abs(slope) <= 0.018 and abs(direction_recent_average - direction_baseline) <= max(
        1, direction_baseline * 0.25
    ):
        long_term_direction = "Flat"
    else:
        long_term_direction = "Irregular"

    if current_drought_days >= 180 and recent_average == 0:
        recent_activity = "Dormant"
    elif has_recent_revival:
        recent_activity = "Revived"
    elif recent_average >= max(1, baseline_average * 1.15):
        recent_activity = "Active recently"
    elif recent_average <= baseline_average * 0.55:
        recent_activity = "Quiet recently"
    else:
        recent_activity = "Typical recently"

    if has_early_spike:
        shape = "Early spike"
    elif is_spiky:
        shape = "Spike-driven"
    elif (
        peak_month_share <= 0.12
        and len([value for value in monthly_values if value > 0]) >= len(monthly_values) * 0.5
    ):
        shape = "Steady"
    else:
        shape = "Mixed"

    return {
        "label": long_term_direction,
        "longTermDirection": long_term_direction,
        "recentActivity": recent_activity,
        "shape": shape,
        "firstHalfAverage": launch_average,
        "secondHalfAverage": recent_average,
        "delta": delta,
        "percentChange": percent_change,
        "falloffScore": falloff_score,
        "baselineAverage": baseline_average,
        "recentAverage": recent_average,
        "previousAverage": previous_average,
        "launchAverage": launch_average,
        "launchShare": launch_share,
        "peakMonthShare": peak_month_share,
        "trendSlope": trend["slope"],
        "trendRSquared": trend["rSquared"],
    }


def playlist_personality(stats):
    if stats["totalTracks"] == 0:
        return "Blank canvas"

    if stats["daysSinceLastAdd"] is not None and stats["daysSinceLastAdd"] >= 365:
        return "Dormant"

    if stats["monthlyTrend"]["longTermDirection"] in {"Increasing", "Decreasing"}:
        return stats["monthlyTrend"]["longTermDirection"]

    if stats["monthlyTrend"]["shape"] in {"Early spike", "Spike-driven"}:
        return stats["monthlyTrend"]["shape"]

    if stats["momentumDelta"] >= 10:
        return "Increasing"

    if stats["biggestSpike"]["count"] >= 25:
        return "Spiky"

    if stats["consistencyScore"] >= 0.55:
        return "Steady"

    return "Variable"


def build_playlist_insight(playlist, added_dates, today=None):
    today = today or date.today()
    dates = parse_added_dates(added_dates)

    if not dates:
        return {
            "playlistId": playlist["id"],
            "name": playlist["name"],
            "totalTracks": 0,
            "firstAddDate": None,
            "lastAddDate": None,
            "daysSinceLastAdd": None,
            "activeDays": 0,
            "activeMonths": 0,
            "averageAddsPerActiveMonth": 0,
            "addsLast90Days": 0,
            "addsPrevious90Days": 0,
            "momentumDelta": 0,
            "longestDroughtDays": 0,
            "mostActiveMonth": None,
            "mostActiveSeason": None,
            "biggestSpike": {"label": None, "count": 0},
            "consistencyScore": 0,
            "monthlyTrend": build_monthly_trend([], today),
            "personality": "Blank canvas",
        }

    first_date = dates[0]
    last_date = dates[-1]
    month_labels = [item.strftime("%Y-%m") for item in dates]
    season_labels = [month_to_season(str(item.year), f"{item.month:02d}") for item in dates]
    active_months = len(set(month_labels))
    total_months = month_range_count(first_date.strftime("%Y-%m"), last_date.strftime("%Y-%m"))
    adds_last_90 = sum(1 for item in dates if 0 <= (today - item).days <= 90)
    adds_previous_90 = sum(1 for item in dates if 90 < (today - item).days <= 180)
    biggest_spike = most_common_bucket(month_labels) or {"label": None, "count": 0}
    stats = {
        "playlistId": playlist["id"],
        "name": playlist["name"],
        "totalTracks": len(dates),
        "firstAddDate": first_date.isoformat(),
        "lastAddDate": last_date.isoformat(),
        "daysSinceLastAdd": (today - last_date).days,
        "activeDays": (last_date - first_date).days + 1,
        "activeMonths": active_months,
        "averageAddsPerActiveMonth": round(len(dates) / active_months, 1),
        "addsLast90Days": adds_last_90,
        "addsPrevious90Days": adds_previous_90,
        "momentumDelta": adds_last_90 - adds_previous_90,
        "longestDroughtDays": longest_gap_days(dates),
        "mostActiveMonth": most_common_bucket(month_labels),
        "mostActiveSeason": most_common_bucket(season_labels),
        "biggestSpike": biggest_spike,
        "consistencyScore": round(active_months / total_months, 2) if total_months else 0,
        "monthlyTrend": build_monthly_trend(dates, today),
    }
    stats["personality"] = playlist_personality(stats)

    return stats


def pick_ranked(insights, key, reverse=True):
    ranked = sorted(
        (insight for insight in insights if insight["totalTracks"] > 0),
        key=key,
        reverse=reverse,
    )

    return ranked[0] if ranked else None


def build_insights_response(playlists, insights):
    total_tracks = sum(insight["totalTracks"] for insight in insights)
    total_recent = sum(insight["addsLast90Days"] for insight in insights)
    total_previous = sum(insight["addsPrevious90Days"] for insight in insights)
    all_first_dates = [insight["firstAddDate"] for insight in insights if insight["firstAddDate"]]
    all_last_dates = [insight["lastAddDate"] for insight in insights if insight["lastAddDate"]]

    rankings = {
        "mostRecentlyActive": pick_ranked(
            insights,
            lambda insight: insight["daysSinceLastAdd"],
            reverse=False,
        ),
        "mostDormant": pick_ranked(
            insights,
            lambda insight: insight["daysSinceLastAdd"],
        ),
        "biggestRecentMomentum": pick_ranked(
            insights,
            lambda insight: insight["momentumDelta"],
        ),
        "biggestSpike": pick_ranked(
            insights,
            lambda insight: insight["biggestSpike"]["count"],
        ),
        "longestDrought": pick_ranked(
            insights,
            lambda insight: insight["longestDroughtDays"],
        ),
        "mostConsistent": pick_ranked(
            insights,
            lambda insight: insight["consistencyScore"],
        ),
        "biggestFalloff": pick_ranked(
            insights,
            lambda insight: insight.get("monthlyTrend", {}).get("falloffScore", 0),
        ),
    }

    return {
        "summary": {
            "playlistCount": len(playlists),
            "totalTracks": total_tracks,
            "addsLast90Days": total_recent,
            "addsPrevious90Days": total_previous,
            "momentumDelta": total_recent - total_previous,
            "firstAddDate": min(all_first_dates) if all_first_dates else None,
            "lastAddDate": max(all_last_dates) if all_last_dates else None,
        },
        "rankings": rankings,
        "playlists": insights,
    }


def playlist_item_track(playlist_item):
    return playlist_item.get("track") or playlist_item.get("item") or {}


def album_image_url(track):
    album = track.get("album") or {}
    images = album.get("images") or []
    return images[0].get("url") if images else None


def normalize_top_track(track, rank=None, time_range=None):
    artists = track.get("artists") or []
    album = track.get("album") or {}

    return {
        "id": track.get("id"),
        "name": track.get("name") or "Unknown track",
        "artists": [artist.get("name") or "Unknown artist" for artist in artists],
        "artistIds": [artist.get("id") for artist in artists if artist.get("id")],
        "albumName": album.get("name"),
        "imageUrl": album_image_url(track),
        "rank": rank,
        "timeRange": time_range,
    }


def normalize_top_artist(artist, rank=None, time_ranges=None, playlist_track_count=0):
    images = artist.get("images") or []

    return {
        "id": artist.get("id"),
        "name": artist.get("name") or "Unknown artist",
        "imageUrl": images[0].get("url") if images else None,
        "rank": rank,
        "timeRanges": time_ranges or [],
        "playlistTrackCount": playlist_track_count,
    }


def ranked_items(items):
    return {
        item.get("id"): {"rank": index + 1, "item": item}
        for index, item in enumerate(items)
        if item.get("id")
    }


def playlist_track_objects(playlist_items):
    tracks = []

    for playlist_item in playlist_items:
        track = playlist_item_track(playlist_item)

        if track and track.get("id"):
            tracks.append(track)

    return tracks


def matched_top_tracks(playlist_tracks, top_tracks, time_range):
    playlist_track_ids = {track.get("id") for track in playlist_tracks if track.get("id")}
    matches = []

    for index, track in enumerate(top_tracks):
        if track.get("id") in playlist_track_ids:
            matches.append(normalize_top_track(track, index + 1, time_range))

    return matches


def matched_top_artists(playlist_tracks, top_artists_by_range):
    artist_counts = Counter()
    artist_by_id = {}

    for track in playlist_tracks:
        for artist in track.get("artists") or []:
            artist_id = artist.get("id")

            if artist_id:
                artist_counts[artist_id] += 1
                artist_by_id[artist_id] = artist

    ranked_artists_by_range = {
        time_range: ranked_items(artists) for time_range, artists in top_artists_by_range.items()
    }
    artist_matches = []

    for artist_id, playlist_track_count in artist_counts.items():
        matched_ranges = [
            time_range
            for time_range, artists in ranked_artists_by_range.items()
            if artist_id in artists
        ]

        if not matched_ranges:
            continue

        best_rank = min(
            ranked_artists_by_range[time_range][artist_id]["rank"] for time_range in matched_ranges
        )
        top_artist = ranked_artists_by_range[matched_ranges[0]][artist_id]["item"]
        artist_matches.append(
            normalize_top_artist(
                top_artist or artist_by_id[artist_id],
                best_rank,
                matched_ranges,
                playlist_track_count,
            )
        )

    return sorted(
        artist_matches,
        key=lambda artist: (
            artist["rank"] or TOP_ITEM_LIMIT + 1,
            -artist["playlistTrackCount"],
            artist["name"],
        ),
    )


def build_playlist_wrapped(playlist, playlist_items, top_tracks_by_range, top_artists_by_range):
    playlist_tracks = playlist_track_objects(playlist_items)
    current_favorites = matched_top_tracks(
        playlist_tracks,
        top_tracks_by_range.get("short_term", []),
        "short_term",
    )
    all_time_favorites = matched_top_tracks(
        playlist_tracks,
        top_tracks_by_range.get("long_term", []),
        "long_term",
    )
    artist_gravity = matched_top_artists(playlist_tracks, top_artists_by_range)

    return {
        "playlistId": playlist["id"],
        "name": playlist["name"],
        "trackCount": len(playlist_tracks),
        "tasteMatch": {
            "topTrackLimit": TOP_ITEM_LIMIT,
            "shortTermMatched": len(current_favorites),
            "longTermMatched": len(all_time_favorites),
            "shortTermPercent": round(len(current_favorites) / TOP_ITEM_LIMIT * 100, 1),
            "longTermPercent": round(len(all_time_favorites) / TOP_ITEM_LIMIT * 100, 1),
        },
        "currentFavorites": current_favorites[:8],
        "allTimeFavorites": all_time_favorites[:8],
        "artistGravity": artist_gravity[:8],
    }


def build_wrapped_response(
    playlists, playlist_items_by_id, top_tracks_by_range, top_artists_by_range
):
    playlist_wrapped = [
        build_playlist_wrapped(
            playlist,
            playlist_items_by_id.get(playlist["id"], []),
            top_tracks_by_range,
            top_artists_by_range,
        )
        for playlist in playlists
    ]

    return {
        "topTrackLimit": TOP_ITEM_LIMIT,
        "playlists": playlist_wrapped,
    }


@app.route("/")
def serve():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/session")
def session():
    return jsonify({"authenticated": get_token() is not None})


@app.route("/api/login")
def login():
    global oauth_state
    try:
        oauth_state = secrets.token_urlsafe(32)
        return jsonify({"url": get_spotify_oauth().get_authorize_url(state=oauth_state)})
    except RuntimeError:
        logging.exception("Spotify OAuth configuration is incomplete")
        return jsonify({"error": "Spotify OAuth is not configured"}), 503


@app.route("/callback")
def callback():
    try:
        code = request.args.get("code")
        state = request.args.get("state")

        if not code:
            return jsonify({"error": "Missing Spotify authorization code"}), 400

        global oauth_state, token_info
        if not oauth_state or not state or not secrets.compare_digest(state, oauth_state):
            return jsonify({"error": "Invalid OAuth state"}), 400

        oauth_state = None
        oauth = get_spotify_oauth()
        token_info = oauth.get_access_token(code)

        if not token_info or "access_token" not in token_info:
            return jsonify({"error": "Failed to get token_info"}), 500

        oauth.cache_handler.save_token_to_cache(token_info)
        return redirect("/")
    except Exception:
        logging.exception("Error in callback")
        return jsonify({"error": "Spotify authentication failed"}), 500


@app.route("/api/playlists")
def playlists():
    active_token, error_response = require_token()

    if error_response:
        return error_response

    try:
        return jsonify(get_cached_playlists(spotify_client(active_token)))
    except Exception:
        logging.exception("Error fetching playlists")
        return jsonify({"error": "Unable to fetch playlists from Spotify"}), 502


@app.route("/api/analyze", methods=["POST"])
def analyze():
    active_token, error_response = require_token()

    if error_response:
        return error_response

    data = request.get_json() or {}
    playlist_ids = normalize_playlist_ids(data)
    view_mode = data.get("viewMode", "month")
    chart_mode = data.get("chartMode", "sum")
    start = data.get("start", "start")

    if not playlist_ids:
        return jsonify({"error": "No playlist IDs provided"}), 400

    if len(playlist_ids) > MAX_SELECTED_PLAYLISTS:
        return jsonify({"error": "Too many playlist IDs"}), 400

    if view_mode not in {"month", "season"}:
        return jsonify({"error": "Invalid view mode"}), 400

    if chart_mode not in {"sum", "compare"}:
        return jsonify({"error": "Invalid chart mode"}), 400

    sp = spotify_client(active_token)

    try:
        playlists_by_id = {playlist["id"]: playlist for playlist in get_cached_playlists(sp)}
        unknown_ids = [
            playlist_id for playlist_id in playlist_ids if playlist_id not in playlists_by_id
        ]
        if unknown_ids:
            return jsonify({"error": "Unknown playlist ID"}), 400

        analyses = [
            fetch_playlist_analysis(
                sp,
                playlist_id,
                playlists_by_id.get(playlist_id, {}).get("name", playlist_id),
                view_mode,
                start,
            )
            for playlist_id in playlist_ids
        ]

        return jsonify(build_analysis_response(analyses, view_mode, chart_mode))
    except ValueError as error:
        logging.exception("ValueError during analysis")
        return jsonify({"error": str(error)}), 400
    except Exception:
        logging.exception("Error during analysis")
        return jsonify({"error": "Unable to analyze playlists"}), 502


@app.route("/api/insights", methods=["POST"])
def insights():
    active_token, error_response = require_token()

    if error_response:
        return error_response

    data = request.get_json() or {}
    playlist_ids = normalize_playlist_ids(data)

    if not playlist_ids:
        return jsonify({"error": "No playlist IDs provided"}), 400

    if len(playlist_ids) > MAX_SELECTED_PLAYLISTS:
        return jsonify({"error": "Too many playlist IDs"}), 400

    sp = spotify_client(active_token)

    try:
        playlists_by_id = {playlist["id"]: playlist for playlist in get_cached_playlists(sp)}
        if any(playlist_id not in playlists_by_id for playlist_id in playlist_ids):
            return jsonify({"error": "Unknown playlist ID"}), 400

        selected_playlists = [
            playlists_by_id.get(playlist_id, {"id": playlist_id, "name": playlist_id})
            for playlist_id in playlist_ids
        ]
        playlist_insights = [
            build_playlist_insight(
                playlist,
                get_cached_added_dates(sp, playlist["id"]),
            )
            for playlist in selected_playlists
        ]

        return jsonify(build_insights_response(selected_playlists, playlist_insights))
    except Exception:
        logging.exception("Error during insights")
        return jsonify({"error": "Unable to build playlist insights"}), 502


@app.route("/api/wrapped", methods=["POST"])
def wrapped():
    active_token, error_response = require_token()

    if error_response:
        return error_response

    data = request.get_json() or {}
    playlist_ids = normalize_playlist_ids(data)

    if not playlist_ids:
        return jsonify({"error": "No playlist IDs provided"}), 400

    if len(playlist_ids) > MAX_SELECTED_PLAYLISTS:
        return jsonify({"error": "Too many playlist IDs"}), 400

    sp = spotify_client(active_token)

    try:
        playlists_by_id = {playlist["id"]: playlist for playlist in get_cached_playlists(sp)}
        if any(playlist_id not in playlists_by_id for playlist_id in playlist_ids):
            return jsonify({"error": "Unknown playlist ID"}), 400

        selected_playlists = [
            playlists_by_id.get(playlist_id, {"id": playlist_id, "name": playlist_id})
            for playlist_id in playlist_ids
        ]
        top_tracks_by_range = {
            "short_term": get_cached_top_items(sp, "tracks", "short_term"),
            "long_term": get_cached_top_items(sp, "tracks", "long_term"),
        }
        top_artists_by_range = {
            "short_term": get_cached_top_items(sp, "artists", "short_term"),
            "long_term": get_cached_top_items(sp, "artists", "long_term"),
        }
        playlist_items_by_id = {
            playlist["id"]: get_cached_playlist_tracks(sp, playlist["id"])
            for playlist in selected_playlists
        }

        return jsonify(
            build_wrapped_response(
                selected_playlists,
                playlist_items_by_id,
                top_tracks_by_range,
                top_artists_by_range,
            )
        )
    except SpotifyException as error:
        if getattr(error, "http_status", None) in {401, 403}:
            return jsonify(
                {
                    "error": (
                        "Wrapped data needs Spotify top-track permission. "
                        "Log out and log back in once."
                    )
                }
            ), 403

        logging.exception("Spotify error during wrapped")
        return jsonify({"error": "Spotify rejected the Wrapped request"}), 502
    except Exception:
        logging.exception("Error during wrapped")
        return jsonify({"error": "Unable to build Wrapped data"}), 502


@app.route("/api/logout", methods=["POST"])
def logout():
    global token_info, playlist_cache, playlist_tracks_cache, added_dates_cache, top_items_cache
    token_info = None
    playlist_cache = None
    playlist_tracks_cache = {}
    added_dates_cache = {}
    top_items_cache = {}

    try:
        if os.path.exists(TOKEN_CACHE_PATH):
            os.remove(TOKEN_CACHE_PATH)
    except Exception:
        logging.exception("Error during logout")
        return jsonify({"error": "Unable to clear the local token cache"}), 500

    return jsonify({"message": "Logged out successfully"}), 200


@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(app.static_folder, path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8888")),
    )
