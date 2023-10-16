import argparse
import datetime
import json
import logging
import os
import sys
# enable relative path
# To do: change file structure in the future
from pathlib import Path

import openai
import spotipy

path = str(Path(Path(__file__).parent.absolute()).parent.absolute())
sys.path.insert(0, path)

from shared_lib.get_credential import read_credentials

logging.basicConfig()
logger = logging.getLogger("playlist_generate")
logger.setLevel(logging.INFO)


def create_playlist(prompt, num_of_songs=8, model="gtp-3.5-turbo"):
    example_json = """
    [
      {"song": "Don't Stop Believin", "artist": "Journey"},
      {"song": "Happy", "artist": "Pharrell Williams"},
      {"song": "Here Comes the Sun", "artist": "The Beatles"},
      {"song": "Walking on Sunshine", "artist": "Katrina and The Waves"},
      {"song": "Good Vibrations", "artist": "The Beach Boys"}
    ]
    """
    messages = [
        {
            "role": "system",
            "content": """You are a helpful playlist generating assistant. 
            You should generate a list of songs and their artists according to a text prompt. 
            Your should return a JSON array, where each element follows this format: {"song": <song_title>, "artist": <artist_name>}""",
        },
        {
            "role": "user",
            "content": "Generate a playlist of 5 songs based on this prompt: super super sad songs",
        },
        {"role": "assistant", "content": example_json},
        {
            "role": "user",
            "content": f"Generate a playlist of {num_of_songs} songs based on this prompt: {prompt}",
        },
    ]

    response = openai.ChatCompletion.create(
        messages=messages, model=model, max_tokens=400
    )

    playlist = json.loads(response["choices"][0]["message"]["content"])
    return playlist


def add_songs_to_spotify(playlist_prompt, playlist, credentials):
    spotipy_client_id = credentials["SPOTIFY_CLIENT_ID"]
    spotipy_client_secret = credentials["SPOTIFY_CLIENT_SECRET"]
    spotipy_redirect_url = "http://localhost:9999"

    sp = spotipy.Spotify(
        auth_manager=spotipy.SpotifyOAuth(
            client_id=spotipy_client_id,
            client_secret=spotipy_client_secret,
            redirect_uri=spotipy_redirect_url,
            scope="playlist-modify-private",
        )
    )
    current_user = sp.current_user()

    if current_user:
        track_uris = []
        for item in playlist:
            # query songs based on the playlist
            artist, song = item["artist"], item["song"]
            basic_query = f"{song} {artist}"
            advanced_query = f"artist:({artist}) track:({song})"

            for query in [basic_query, advanced_query]:
                logger.debug(f"Searching for query: {query}")
                search_results = sp.search(q=query, limit=10, type="track")

                # do not use songs that is not popular as it may not be a good track
                if (
                    not search_results["tracks"]["items"]
                    or search_results["tracks"]["items"][0]["popularity"] < 20
                ):
                    continue
                else:
                    result = search_results["tracks"]["items"][0]
                    logger.info(f"Found: {result['name']} [{result['id']}]")
                    track_uris.append(result["id"])
                    break

            else:
                logger.info(
                    f"Queries {advanced_query} and {basic_query} returned no good results. Skipping."
                )

        # create an empty playlist
        created_playlist = sp.user_playlist_create(
            current_user["id"],
            public=False,
            name=f"{playlist_prompt} ({datetime.datetime.now().strftime('%c')})",
        )

        # add tracks
        sp.user_playlist_add_tracks(
            current_user["id"], created_playlist["id"], track_uris
        )

        logger.info(f"Created playlist: {created_playlist['name']}")
        logger.info(created_playlist["external_urls"]["spotify"])
    else:
        raise ValueError("Error: invalid spotify user!")


def main(playlist_prompt, num_of_songs, credentials, model):
    # connect to openai api
    openai.api_key = credentials["OPENAI_API_KEY"]

    playlist = create_playlist(playlist_prompt, num_of_songs, model)
    add_songs_to_spotify(playlist_prompt, playlist, credentials)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Python command line spotify playlist generator"
    )
    parser.add_argument("-p", type=str, help="The prompt to describing the playlist.")
    parser.add_argument(
        "-m",
        type=str,
        default="gtp-3.5-turbo",
        help="The openAI models (gtp-3.5-turbo, gtp-4) to be used.",
    )
    parser.add_argument(
        "-n",
        type=int,
        default="10",
        help="The number of songs between 1 and 30 to be added.",
    )
    parser.add_argument(
        "-e",
        type=str,
        default=".env",
        required=False,
        help='A file contains your credentials: "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "OPENAI_API_KEY"',
    )

    args = parser.parse_args()
    credentials = read_credentials(args.e)
    if (
        "SPOTIFY_CLIENT_ID" not in credentials.keys()
        or "SPOTIFY_CLIENT_SECRET" not in credentials.keys()
        or "OPENAI_API_KEY" not in credentials.keys()
    ):
        raise ValueError(
            "Error: missing 1 or more credentials, please review your credential file"
        )

    model = args.m
    logger.info(f"Using model: {model}")
    if model != "gpt-4" and model != "gpt-3.5-turbo":
        raise ValueError(
            "Error: model name is not valid, please select either gpt-4 or gpt-3.5-turbo"
        )

    playlist_prompt = args.p
    num_of_songs = args.n
    if num_of_songs < 1 or num_of_songs > 30:
        raise ValueError("Error: num of songs should be between 0 and 30")

    main(playlist_prompt, num_of_songs, credentials, model)
