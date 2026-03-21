from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

load_dotenv()

app = FastAPI(title="SongDrop")
app.mount("/static", StaticFiles(directory="static"), name="static")


def get_spotify():
    return spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    ))

@app.get("/")
def index():
    return FileResponse("static/index.html")


def fetch_tracks(playlist_url: str) -> list[dict]:
    sp = get_spotify()
    
    # Extract playlist ID from URL
    playlist_id = playlist_url.split("/playlist/")[-1].split("?")[0]
    
    tracks = []
    offset = 0
    
    while True:
        results = sp.playlist_tracks(
            playlist_id,
            limit=50,
            offset=offset,
            fields="items(track(name,artists,preview_url,album(images))),next"
        )
        
        for item in results["items"]:
            track = item.get("track")
            if not track or not track.get("preview_url"):
                continue
            tracks.append({
                "name": track["name"],
                "artist": track["artists"][0]["name"],
                "preview_url": track["preview_url"],
                "album_art": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
            })
        
        if not results.get("next"):
            break
        offset += 50

    if not tracks:
        raise HTTPException(status_code=404, detail="No playable tracks found in this playlist.")
    
    return tracks

@app.get("/playlist")
def get_playlist(url: str):
    try:
        tracks = fetch_tracks(url)
        return {"tracks": tracks}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

import os

@app.get("/debug-env")
def debug_env():
    return {
        "client_id_set": bool(os.getenv("SPOTIPY_CLIENT_ID")),
        "client_secret_set": bool(os.getenv("SPOTIPY_CLIENT_SECRET")),
        "client_id_preview": os.getenv("SPOTIPY_CLIENT_ID", "")[:4] + "...",
    }

@app.get("/debug-spotify")
def debug_spotify():
    try:
        sp = get_spotify()
        # Try a simple search instead of playlist
        results = sp.search(q="test", type="track", limit=1)
        return {"status": "ok", "track": results["tracks"]["items"][0]["name"]}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    
@app.get("/debug-playlist")
def debug_playlist(url: str):
    try:
        sp = get_spotify()
        playlist_id = url.split("/playlist/")[-1].split("?")[0]
        result = sp.playlist(playlist_id, fields="name,tracks.total")
        return {"status": "ok", "name": result["name"], "total": result["tracks"]["total"]}
    except Exception as e:
        return {"status": "error", "detail": str(e), "type": type(e).__name__}