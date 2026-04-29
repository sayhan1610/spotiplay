"""Spotify API Toolkit - Full-featured Spotify API Interface

A comprehensive tool for interacting with the Spotify API, featuring:
- Advanced search (tracks, artists, albums, playlists)
- Detailed track, artist, and album information
- Audio features and analysis
- Playlist management and browsing
- Copy track info to clipboard
- And more features not available in standard Spotify

Required environment variables in .env:
  SPOTIFY_CLIENT_ID=your_spotify_client_id
  SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
  SPOTIFY_REDIRECT_URI=http://127.0.0.1:5000/callback
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
app.secret_key = os.getenv("SECRET_KEY", "spotify-toolkit-secret-key-change-me")

# Add custom Jinja2 filters
@app.template_filter('format_duration')
def format_duration_filter(ms: int) -> str:
    """Format milliseconds to MM:SS."""
    if ms is None:
        return "0:00"
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}:{seconds:02d}"

@app.template_filter('key_name')
def key_name_filter(key: int) -> str:
    """Convert key number to key name."""
    if key is None:
        return "Unknown"
    keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    return keys[key] if 0 <= key < len(keys) else "Unknown"

# Spotify API endpoints
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"

# Token cache for client credentials flow
_token_cache: Dict[str, Any] = {"access_token": None, "expires_at": 0.0}

# Scope for user-related features
SPOTIFY_SCOPES = [
    "user-read-private",
    "user-read-email",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-library-read",
    "user-top-read",
    "user-read-recently-played",
]


# -----------------------------
# Spotify Authentication
# -----------------------------

def get_credentials() -> tuple[str, str, str]:
    """Get Spotify credentials from environment."""
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5000/callback")
    return client_id, client_secret, redirect_uri


def get_client_token() -> str:
    """Get client credentials token (app-level access)."""
    client_id, client_secret, _ = get_credentials()
    if not client_id or not client_secret:
        raise RuntimeError("Missing SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET in .env")

    now = time.time()
    cached_token = _token_cache.get("access_token")
    expires_at = float(_token_cache.get("expires_at") or 0)
    if cached_token and now < expires_at - 30:
        return cached_token

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = requests.post(
        SPOTIFY_TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    access_token = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = now + expires_in
    return access_token


def get_user_token() -> Optional[str]:
    """Get user authorization token if available."""
    return session.get("spotify_token")


def spotify_request(
    method: str,
    endpoint: str,
    token: Optional[str] = None,
    params: Optional[Dict] = None,
    json_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Make authenticated request to Spotify API."""
    if token is None:
        token = get_client_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    url = f"{SPOTIFY_API_BASE}{endpoint}"
    
    # Debug: log the request
    print(f"DEBUG: {method} {url}")
    print(f"DEBUG token: {token[:20]}..." if token else "DEBUG token: None")
    print(f"DEBUG params: {params}")
    
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        json=json_data,
        timeout=30,
    )
    
    # Debug: log response status
    print(f"DEBUG response status: {response.status_code}")
    if response.status_code >= 400:
        print(f"DEBUG response body: {response.text[:500]}")
    
    response.raise_for_status()
    return response.json()


# -----------------------------
# API Routes - Search
# -----------------------------

@app.route("/api/search")
def api_search():
    """Search for tracks, artists, albums, or playlists."""
    query = request.args.get("q", "").strip()
    search_type = request.args.get("type", "track")  # track, artist, album, playlist
    limit = min(int(request.args.get("limit", 20)), 50)
    offset = int(request.args.get("offset", 0))

    if not query:
        return jsonify({"error": "Query is required"}), 400

    # Map search types - Spotify API uses singular (track, artist, album, playlist)
    type_map = {
        "track": "track",
        "tracks": "track",
        "artist": "artist",
        "artists": "artist",
        "album": "album",
        "albums": "album",
        "playlist": "playlist",
        "playlists": "playlist",
    }
    search_type = type_map.get(search_type, "track")

    try:
        # Test with hardcoded values first
        result = spotify_request(
            "GET",
            "/search",
            params={
                "q": query,
                "type": search_type,
                "limit": 10,
                "offset": 0,
            },
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/search/all")
def api_search_all():
    """Search across all types at once."""
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 5)), 10)

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        result = spotify_request(
            "GET",
            "/search",
            params={
                "q": query,
                "type": "track,artist,album,playlist",
                "limit": limit,
            },
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# API Routes - Tracks
# -----------------------------

@app.route("/api/track/<track_id>")
def api_track(track_id: str):
    """Get detailed track information."""
    try:
        track = spotify_request("GET", f"/tracks/{track_id}")
        return jsonify(track)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tracks")
def api_tracks_multiple():
    """Get multiple tracks at once."""
    ids = request.args.get("ids", "").strip()
    if not ids:
        return jsonify({"error": "Track IDs required"}), 400

    try:
        tracks = spotify_request("GET", "/tracks", params={"ids": ids})
        return jsonify(tracks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/track/audio-features/<track_id>")
def api_track_audio_features(track_id: str):
    """Get audio features for a track."""
    try:
        features = spotify_request("GET", f"/audio-features/{track_id}")
        return jsonify(features)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tracks/audio-features")
def api_tracks_audio_features():
    """Get audio features for multiple tracks."""
    ids = request.args.get("ids", "").strip()
    if not ids:
        return jsonify({"error": "Track IDs required"}), 400

    try:
        features = spotify_request("GET", "/audio-features", params={"ids": ids})
        return jsonify(features)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/track/analysis/<track_id>")
def api_track_analysis(track_id: str):
    """Get detailed audio analysis for a track."""
    try:
        analysis = spotify_request("GET", f"/audio-analysis/{track_id}")
        return jsonify(analysis)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# API Routes - Artists
# -----------------------------

@app.route("/api/artist/<artist_id>")
def api_artist(artist_id: str):
    """Get detailed artist information."""
    try:
        artist = spotify_request("GET", f"/artists/{artist_id}")
        return jsonify(artist)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/artists")
def api_artists_multiple():
    """Get multiple artists at once."""
    ids = request.args.get("ids", "").strip()
    if not ids:
        return jsonify({"error": "Artist IDs required"}), 400

    try:
        artists = spotify_request("GET", "/artists", params={"ids": ids})
        return jsonify(artists)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/artist/top-tracks/<artist_id>")
def api_artist_top_tracks(artist_id: str):
    """Get artist's top tracks."""
    country = request.args.get("country", "US")
    try:
        result = spotify_request(
            "GET", f"/artists/{artist_id}/top-tracks", params={"country": country}
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/artist/related-artists/<artist_id>")
def api_artist_related(artist_id: str):
    """Get artists related to this artist."""
    try:
        result = spotify_request("GET", f"/artists/{artist_id}/related-artists")
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/artist/albums/<artist_id>")
def api_artist_albums(artist_id: str):
    """Get artist's albums."""
    include_groups = request.args.get("include_groups", "album,single")
    limit = min(int(request.args.get("limit", 20)), 50)
    offset = int(request.args.get("offset", 0))
    market = request.args.get("market", "US")

    try:
        result = spotify_request(
            "GET",
            f"/artists/{artist_id}/albums",
            params={
                "include_groups": include_groups,
                "limit": limit,
                "offset": offset,
                "market": market,
            },
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# API Routes - Albums
# -----------------------------

@app.route("/api/album/<album_id>")
def api_album(album_id: str):
    """Get detailed album information."""
    market = request.args.get("market", "US")
    try:
        album = spotify_request("GET", f"/albums/{album_id}", params={"market": market})
        return jsonify(album)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/albums")
def api_albums_multiple():
    """Get multiple albums at once."""
    ids = request.args.get("ids", "").strip()
    market = request.args.get("market", "US")
    if not ids:
        return jsonify({"error": "Album IDs required"}), 400

    try:
        albums = spotify_request("GET", "/albums", params={"ids": ids, "market": market})
        return jsonify(albums)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/album/tracks/<album_id>")
def api_album_tracks(album_id: str):
    """Get tracks from an album."""
    limit = min(int(request.args.get("limit", 50)), 50)
    offset = int(request.args.get("offset", 0))
    market = request.args.get("market", "US")

    try:
        tracks = spotify_request(
            "GET",
            f"/albums/{album_id}/tracks",
            params={"limit": limit, "offset": offset, "market": market},
        )
        return jsonify(tracks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# API Routes - Playlists
# -----------------------------

@app.route("/api/playlist/<playlist_id>")
def api_playlist(playlist_id: str):
    """Get playlist details and tracks."""
    market = request.args.get("market", "US")
    limit = min(int(request.args.get("limit", 100)), 100)
    offset = int(request.args.get("offset", 0))

    try:
        playlist = spotify_request(
            "GET",
            f"/playlists/{playlist_id}",
            params={"market": market, "limit": limit, "offset": offset},
        )
        return jsonify(playlist)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/playlist/tracks/<playlist_id>")
def api_playlist_tracks(playlist_id: str):
    """Get tracks from a playlist."""
    market = request.args.get("market", "US")
    limit = min(int(request.args.get("limit", 100)), 100)
    offset = int(request.args.get("offset", 0))

    try:
        result = spotify_request(
            "GET",
            f"/playlists/{playlist_id}/tracks",
            params={"market": market, "limit": limit, "offset": offset},
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# API Routes - User Data
# -----------------------------

@app.route("/api/user/<user_id>")
def api_user(user_id: str):
    """Get user profile."""
    try:
        user = spotify_request("GET", f"/users/{user_id}")
        return jsonify(user)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/me")
def api_current_user():
    """Get current user profile (requires user auth)."""
    token = get_user_token()
    if not token:
        return jsonify({"error": "User authentication required"}), 401

    try:
        user = spotify_request("GET", "/me", token=token)
        return jsonify(user)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/me/top/tracks")
def api_my_top_tracks():
    """Get user's top tracks (requires user auth)."""
    token = get_user_token()
    if not token:
        return jsonify({"error": "User authentication required"}), 401

    time_range = request.args.get("time_range", "medium_term")
    limit = min(int(request.args.get("limit", 20)), 50)

    try:
        tracks = spotify_request(
            "GET",
            "/me/top/tracks",
            token=token,
            params={"time_range": time_range, "limit": limit},
        )
        return jsonify(tracks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/me/top/artists")
def api_my_top_artists():
    """Get user's top artists (requires user auth)."""
    token = get_user_token()
    if not token:
        return jsonify({"error": "User authentication required"}), 401

    time_range = request.args.get("time_range", "medium_term")
    limit = min(int(request.args.get("limit", 20)), 50)

    try:
        artists = spotify_request(
            "GET",
            "/me/top/artists",
            token=token,
            params={"time_range": time_range, "limit": limit},
        )
        return jsonify(artists)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/me/recently-played")
def api_my_recently_played():
    """Get user's recently played tracks (requires user auth)."""
    token = get_user_token()
    if not token:
        return jsonify({"error": "User authentication required"}), 401

    limit = min(int(request.args.get("limit", 50)), 50)

    try:
        tracks = spotify_request(
            "GET",
            "/me/player/recently-played",
            token=token,
            params={"limit": limit},
        )
        return jsonify(tracks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# API Routes - Browse
# -----------------------------

@app.route("/api/browse/featured-playlists")
def api_browse_featured():
    """Get featured playlists."""
    limit = min(int(request.args.get("limit", 20)), 50)
    offset = int(request.args.get("offset", 0))

    try:
        result = spotify_request(
            "GET",
            "/browse/featured-playlists",
            params={"limit": limit, "offset": offset},
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/browse/new-releases")
def api_browse_new_releases():
    """Get new album releases."""
    limit = min(int(request.args.get("limit", 20)), 50)
    offset = int(request.args.get("offset", 0))
    country = request.args.get("country", "US")

    try:
        result = spotify_request(
            "GET",
            "/browse/new-releases",
            params={"limit": limit, "offset": offset, "country": country},
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/browse/categories")
def api_browse_categories():
    """Get available genre categories."""
    limit = min(int(request.args.get("limit", 50)), 50)
    offset = int(request.args.get("offset", 0))

    try:
        result = spotify_request(
            "GET",
            "/browse/categories",
            params={"limit": limit, "offset": offset},
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/browse/category/<category_id>/playlists")
def api_browse_category_playlists(category_id: str):
    """Get playlists for a specific category."""
    limit = min(int(request.args.get("limit", 20)), 50)
    offset = int(request.args.get("offset", 0))
    country = request.args.get("country", "US")

    try:
        result = spotify_request(
            "GET",
            f"/browse/categories/{category_id}/playlists",
            params={"limit": limit, "offset": offset, "country": country},
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# API Routes - Genres & Recommendations
# -----------------------------

@app.route("/api/genres")
def api_genres():
    """Get available genre seeds."""
    try:
        result = spotify_request("GET", "/recommendations/available-genre-seeds")
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/recommendations")
def api_recommendations():
    """Get track recommendations based on seeds."""
    # Parse seed parameters
    seed_tracks = request.args.get("seed_tracks", "").strip()
    seed_artists = request.args.get("seed_artists", "").strip()
    seed_genres = request.args.get("seed_genres", "").strip()

    if not seed_tracks and not seed_artists and not seed_genres:
        return jsonify({"error": "At least one seed (tracks, artists, or genres) required"}), 400

    limit = min(int(request.args.get("limit", 20)), 100)
    market = request.args.get("market", "US")

    params = {"limit": limit, "market": market}

    if seed_tracks:
        params["seed_tracks"] = seed_tracks
    if seed_artists:
        params["seed_artists"] = seed_artists
    if seed_genres:
        params["seed_genres"] = seed_genres

    # Add target attributes
    for attr in ["tempo", "energy", "danceability", "valence", "acousticness", 
                 "instrumentalness", "liveness", "speechiness", "loudness", "key", "mode"]:
        value = request.args.get(f"target_{attr}")
        if value:
            params[f"target_{attr}"] = value

    try:
        result = spotify_request("GET", "/recommendations", params=params)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# Authentication Routes
# -----------------------------

@app.route("/login")
def login():
    """Redirect to Spotify authorization page."""
    client_id, _, redirect_uri = get_credentials()
    if not client_id:
        return jsonify({"error": "SPOTIFY_CLIENT_ID not configured"}), 500

    scope = " ".join(SPOTIFY_SCOPES)
    auth_url = (
        f"{SPOTIFY_AUTH_URL}"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
    )
    return redirect(auth_url)


@app.route("/callback")
def callback():
    """Handle Spotify OAuth callback."""
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "No authorization code provided"}), 400

    client_id, client_secret, redirect_uri = get_credentials()

    # Exchange code for token
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = requests.post(
        SPOTIFY_TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=15,
    )

    if response.status_code != 200:
        return jsonify({"error": "Failed to obtain access token"}), 400

    data = response.json()
    session["spotify_token"] = data.get("access_token")
    session["spotify_refresh"] = data.get("refresh_token")
    session["spotify_expires"] = time.time() + data.get("expires_in", 3600)

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    """Clear user session."""
    session.clear()
    return redirect(url_for("index"))


# -----------------------------
# Utility Functions
# -----------------------------

def extract_id_from_uri(uri: str) -> str:
    """Extract ID from Spotify URI or URL."""
    # Handle various formats
    # spotify:track:xxx
    # https://open.spotify.com/track/xxx
    # just the ID
    
    if uri.startswith("spotify:"):
        return uri.split(":")[-1]
    
    # Handle URLs
    match = re.search(r"/([a-zA-Z0-9]+)(?:\?|$)", uri)
    if match:
        return match.group(1)
    
    return uri


# -----------------------------
# Frontend Routes
# -----------------------------

@app.route("/")
def index():
    """Main dashboard page."""
    return render_template("index.html")


@app.route("/search")
def search_page():
    """Search page."""
    return render_template("search.html")


@app.route("/track/<track_id>")
def track_page(track_id: str):
    """Track details page."""
    try:
        track = spotify_request("GET", f"/tracks/{track_id}")
        features = spotify_request("GET", f"/audio-features/{track_id}")
        return render_template("track.html", track=track, features=features)
    except Exception as e:
        return render_template("error.html", error=str(e))


@app.route("/artist/<artist_id>")
def artist_page(artist_id: str):
    """Artist details page."""
    try:
        artist = spotify_request("GET", f"/artists/{artist_id}")
        top_tracks = spotify_request(
            "GET", f"/artists/{artist_id}/top-tracks", params={"country": "US"}
        )
        related = spotify_request("GET", f"/artists/{artist_id}/related-artists")
        albums = spotify_request(
            "GET", f"/artists/{artist_id}/albums", params={"include_groups": "album,single", "limit": 12}
        )
        return render_template(
            "artist.html", 
            artist=artist, 
            top_tracks=top_tracks.get("tracks", []),
            related=related.get("artists", []),
            albums=albums.get("items", [])
        )
    except Exception as e:
        return render_template("error.html", error=str(e))


@app.route("/album/<album_id>")
def album_page(album_id: str):
    """Album details page."""
    try:
        album = spotify_request("GET", f"/albums/{album_id}", params={"market": "US"})
        return render_template("album.html", album=album)
    except Exception as e:
        return render_template("error.html", error=str(e))


@app.route("/playlist/<playlist_id>")
def playlist_page(playlist_id: str):
    """Playlist details page."""
    try:
        playlist = spotify_request(
            "GET", f"/playlists/{playlist_id}", params={"market": "US", "limit": 50}
        )
        return render_template("playlist.html", playlist=playlist)
    except Exception as e:
        return render_template("error.html", error=str(e))


@app.route("/browse")
def browse_page():
    """Browse featured content."""
    try:
        featured = spotify_request("GET", "/browse/featured-playlists", params={"limit": 20})
        new_releases = spotify_request("GET", "/browse/new-releases", params={"limit": 20, "country": "US"})
        categories = spotify_request("GET", "/browse/categories", params={"limit": 50})
        return render_template(
            "browse.html",
            featured=featured.get("playlists", {}).get("items", []),
            releases=new_releases.get("albums", {}).get("items", []),
            categories=categories.get("categories", {}).get("items", [])
        )
    except Exception as e:
        return render_template("error.html", error=str(e))


@app.route("/recommendations")
def recommendations_page():
    """Recommendations page."""
    try:
        genres = spotify_request("GET", "/recommendations/available-genre-seeds")
        return render_template("recommendations.html", genres=genres.get("genres", []))
    except Exception as e:
        return render_template("error.html", error=str(e))


@app.route("/analyzer")
def analyzer_page():
    """Audio analyzer page."""
    return render_template("analyzer.html")


# -----------------------------
# Error Handlers
# -----------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", error="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", error="Server error"), 500


# -----------------------------
# Entry Point
# -----------------------------

if __name__ == "__main__":
    # Check for credentials
    client_id, client_secret, _ = get_credentials()
    if not client_id or not client_secret:
        print("WARNING: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in .env")
        print("Get your credentials at: https://developer.spotify.com/dashboard")
    
    app.run(debug=True, host="0.0.0.0", port=5000)