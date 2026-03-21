import os
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

app = FastAPI(title="SongDrop")
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory token store: session_id -> token_info
sessions: dict[str, dict] = {}

SCOPE = "playlist-read-private playlist-read-collaborative streaming user-read-playback-state user-modify-playback-state user-read-email user-read-private"


def get_oauth():
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
        scope=SCOPE,
    )


def get_spotify_for_session(session_id: str) -> spotipy.Spotify:
    token_info = sessions.get(session_id)
    if not token_info:
        raise HTTPException(status_code=401, detail="Not logged in.")

    # Refresh token if expired
    oauth = get_oauth()
    if oauth.is_token_expired(token_info):
        token_info = oauth.refresh_access_token(token_info["refresh_token"])
        sessions[session_id] = token_info

    return spotipy.Spotify(auth=token_info["access_token"])

def fetch_tracks(sp: spotipy.Spotify, playlist_url: str) -> list[dict]:
    playlist_id = playlist_url.split("/playlist/")[-1].split("?")[0]
    tracks = []
    offset = 0

    while True:
        results = sp.playlist_tracks(
            playlist_id,
            limit=50,
            offset=offset,
        )

        for item in results["items"]:
            track = item.get("track")
            if not track or not track.get("uri"):
                continue
            tracks.append({
                "name": track["name"],
                "artist": track["artists"][0]["name"],
                "uri": track["uri"],
                "duration_ms": track["duration_ms"],
                "album_art": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
            })

        # Correct pagination check
        if results["next"] is None:
            break
        offset += 50

    if not tracks:
        raise HTTPException(status_code=404, detail="No tracks found in this playlist.")

    return tracks
@app.get("/me")
def get_me(session_id: str):
    sp = get_spotify_for_session(session_id)
    try:
        user = sp.me()
        token_info = sessions.get(session_id)
        return {
            "name": user["display_name"],
            "logged_in": True,
            "access_token": token_info["access_token"],  # ← add this
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/login")
def login():
    """Redirect user to Spotify login page."""
    oauth = get_oauth()
    auth_url = oauth.get_authorize_url()
    return RedirectResponse(auth_url)


@app.get("/callback")
def callback(code: str, request: Request):
    """Spotify redirects here after login."""
    oauth = get_oauth()
    token_info = oauth.get_access_token(code)

    # Create a session ID and store the token
    session_id = str(uuid.uuid4())
    sessions[session_id] = token_info

    # Redirect to frontend with session ID
    return RedirectResponse(f"/?session={session_id}")


@app.get("/playlist")
def get_playlist(url: str, session_id: str):
    sp = get_spotify_for_session(session_id)
    try:
        tracks = fetch_tracks(sp, url)
        return {"tracks": tracks}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/me")
def get_me(session_id: str):
    """Check if session is valid and return user info."""
    sp = get_spotify_for_session(session_id)
    try:
        user = sp.me()
        return {"name": user["display_name"], "logged_in": True}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))