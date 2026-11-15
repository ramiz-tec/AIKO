import webbrowser


SPOTIFY_LIKED_SONGS_URL = "https://open.spotify.com/collection/tracks"


def PlaySpotifyLikedSongs() -> bool:
    if not webbrowser.open(SPOTIFY_LIKED_SONGS_URL):
        raise RuntimeError("Could not open Spotify Liked Songs in a browser.")
    return True
