"""SpotiPlay - Spotify Playlists Showcase

Single-file Flask app for a curated list of public Spotify playlists.

Expected folder layout:
  - app.py
  - playlists.json
  - .env

playlists.json example:
[
  "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
  "37i9dQZF1DX0XUsuxWHRQd"
]

Required environment variables in .env:
  CLIENT_ID=your_spotify_client_id
  CLIENT_SECRET=your_spotify_client_secret
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from flask import Flask, jsonify, render_template

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent
PLAYLISTS_FILE = BASE_DIR / "playlists.json"

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
PLAYLIST_ID_RE = re.compile(r"playlist/([A-Za-z0-9]+)")

_token_cache: Dict[str, Any] = {"access_token": None, "expires_at": 0.0}
_playlist_cache: Dict[str, Dict[str, Any]] = {}


# -----------------------------
# Spotify helpers
# -----------------------------

def get_credentials() -> tuple[str, str]:
    client_id = os.getenv("CLIENT_ID", "").strip()
    client_secret = os.getenv("CLIENT_SECRET", "").strip()
    return client_id, client_secret


def get_access_token() -> str:
    client_id, client_secret = get_credentials()
    if not client_id or not client_secret:
        raise RuntimeError("Missing CLIENT_ID or CLIENT_SECRET in .env")

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


def extract_playlist_id(value: str) -> str:
    value = str(value).strip()
    if not value:
        raise ValueError("Empty playlist value")

    if re.fullmatch(r"[A-Za-z0-9]+", value):
        return value

    match = PLAYLIST_ID_RE.search(value)
    if match:
        return match.group(1)

    if "spotify.com" in value:
        pieces = value.split("/")
        for idx, piece in enumerate(pieces):
            if piece == "playlist" and idx + 1 < len(pieces):
                return pieces[idx + 1].split("?")[0].split("#")[0]

    raise ValueError(f"Could not extract playlist ID from: {value}")


def load_playlist_ids() -> List[str]:
    if not PLAYLISTS_FILE.exists():
        return []

    try:
        with PLAYLISTS_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in playlists.json: {exc}") from exc

    if not isinstance(raw, list):
        raise RuntimeError("playlists.json must contain a JSON list")

    playlist_ids: List[str] = []
    for item in raw:
        if isinstance(item, str):
            playlist_ids.append(extract_playlist_id(item))
        elif isinstance(item, dict):
            if "id" in item:
                playlist_ids.append(extract_playlist_id(str(item["id"])))
            elif "url" in item:
                playlist_ids.append(extract_playlist_id(str(item["url"])))
            else:
                raise RuntimeError("Playlist objects must contain an 'id' or 'url'")
        else:
            raise RuntimeError("Each playlist entry must be a string or object")

    # Remove duplicates while preserving order.
    seen = set()
    unique_ids: List[str] = []
    for playlist_id in playlist_ids:
        if playlist_id not in seen:
            seen.add(playlist_id)
            unique_ids.append(playlist_id)
    return unique_ids


def fetch_playlist(playlist_id: str) -> Optional[Dict[str, Any]]:
    if playlist_id in _playlist_cache:
        return _playlist_cache[playlist_id]

    token = get_access_token()
    response = requests.get(
        f"{SPOTIFY_API_BASE}/playlists/{playlist_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params={
            "fields": "id,name,description,images,external_urls.spotify,tracks.total",
        },
        timeout=15,
    )

    if response.status_code == 404:
        return None
    response.raise_for_status()

    data = response.json()
    images = data.get("images") or []
    image_url = images[0].get("url") if images and isinstance(images[0], dict) else None

    playlist = {
        "id": data.get("id"),
        "name": data.get("name") or "Untitled Playlist",
        "description": data.get("description") or "No description available.",
        "image_url": image_url,
        "spotify_url": (data.get("external_urls") or {}).get("spotify"),
        "track_count": (data.get("tracks") or {}).get("total", 0),
    }
    _playlist_cache[playlist_id] = playlist
    return playlist


def get_playlists() -> List[Dict[str, Any]]:
    playlists: List[Dict[str, Any]] = []
    for playlist_id in load_playlist_ids():
        playlist = fetch_playlist(playlist_id)
        if playlist:
            playlists.append(playlist)
    return playlists


# -----------------------------
# Routes
# -----------------------------

@app.route("/")
def index():
    try:
        playlists = get_playlists()
        return render_template('index.html', playlists=playlists)
    except Exception as exc:  # pragma: no cover - useful in local dev
        return f"<pre>Application error:\n{exc}</pre>", 500


@app.route("/api/playlists")
def api_playlists():
    return jsonify({"playlists": get_playlists()})


@app.route("/api/playlists/<playlist_id>")
def api_playlist(playlist_id: str):
    playlist = fetch_playlist(extract_playlist_id(playlist_id))
    if not playlist:
        return jsonify({"error": "Playlist not found"}), 404
    return jsonify(playlist)


@app.route("/playlist/<playlist_id>")
def playlist_detail(playlist_id: str):
    playlist = fetch_playlist(extract_playlist_id(playlist_id))
    if not playlist:
        return "Playlist not found", 404
    return render_template('detail.html', playlist=playlist)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True)
