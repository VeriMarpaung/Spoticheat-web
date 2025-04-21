from spotdl import Spotdl
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import subprocess
import os
import sys
import tempfile
import shutil
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()


class SpotifyHandler:
    def __init__(self, token_info=None):
        self.client_id = os.getenv("SPOTIPY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("REDIRECT_URI")
        # self.redirect_uri = "https://verim.pythonanywhere.com/callback"
        # REDIRECT_URI = "http://localhost:8888/callback"
        self.scope = "user-library-read playlist-read-private playlist-read-collaborative"
        self.selected_playlist = None
        self.tracks = []

        self.auth_manager = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope,
            show_dialog=True,
            open_browser=False
        )

        if token_info:
            self.sp = Spotify(auth=token_info['access_token'])
        else:
            self.sp = None

    def get_auth_url(self):
        return self.auth_manager.get_authorize_url()

    def get_playlists(self):
        playlists = self.sp.current_user_playlists()['items']
        return [p['name'] for p in playlists]

    def select_playlist(self, name):
        playlists = self.sp.current_user_playlists()['items']
        for p in playlists:
            if p['name'] == name:
                self.selected_playlist = p['id']
                break

    def get_track_list(self):
        results = self.sp.playlist_tracks(self.selected_playlist)
        self.tracks = [{
            'name': t['track']['name'],
            'artist': t['track']['artists'][0]['name'],
            'url': t['track']['external_urls']['spotify']
        } for t in results['items']]
        return self.tracks

    # def download_selected_tracks(self, selected_urls):
    #     downloaded = []
    #     for url in selected_urls:
    #         print(f"[DEBUG] Downloading: {url}")
    #         try:
    #             result = subprocess.run(
    #                 ["spotdl", url],
    #                 capture_output=True,
    #                 text=True
    #             )
    #             if result.returncode == 0:
    #                 downloaded.append(url)
    #             else:
    #                 downloaded.append(f"Failed: {url} - {result.stderr}")
    #         except Exception as e:
    #             downloaded.append(f"Error: {url} - {str(e)}")
    #     return downloaded

    def download_selected_tracks(self, selected_urls):
        temp_dir = tempfile.mkdtemp()
        downloaded = []
        
        for url in selected_urls:
            print(f"[DEBUG] Downloading: {url}")
            try:
                # Gunakan stdout/stderr langsung ke PIPE tanpa capture_output=True (lebih hemat RAM)
                with open(os.devnull, 'w') as devnull:
                    result = subprocess.run(
                        ["spotdl", url, "--output", temp_dir],
                        stdout=devnull,
                        stderr=devnull,
                        timeout=120  # batasi 2 menit per lagu
                    )
                if result.returncode == 0:
                    downloaded.append(url)
                else:
                    downloaded.append(f"Failed: {url} (non-zero exit)")
            except subprocess.TimeoutExpired:
                downloaded.append(f"Timeout: {url}")
            except Exception as e:
                downloaded.append(f"Error: {url} - {str(e)}")

        zip_path = Path(temp_dir).parent / "songs_downloaded.zip"
        shutil.make_archive(str(zip_path).replace(".zip", ""), 'zip', temp_dir)

        # Bersihkan folder temp setelah ZIP dibuat
        shutil.rmtree(temp_dir, ignore_errors=True)

        return str(zip_path), downloaded




