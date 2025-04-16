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
        self.redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")
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
            cache_path=".cache-web",
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
                result = subprocess.run(
                    ["spotdl", url, "--output", temp_dir],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    downloaded.append(url)
                else:
                    downloaded.append(f"Failed: {url} - {result.stderr}")
            except Exception as e:
                downloaded.append(f"Error: {url} - {str(e)}")

        # ZIP file all downloaded songs
        zip_path = Path(temp_dir).parent / "songs_downloaded.zip"
        # Debug: Print isi folder setelah download
        print("[DEBUG] Isi folder hasil download:", os.listdir(temp_dir))

        if not os.listdir(temp_dir):
            print("[WARNING] Folder kosong. Kemungkinan download gagal.")
            return "", downloaded  # ZIP tidak dibuat karena kosong

        # Buat ZIP
        zip_base_path = str(zip_path).replace(".zip", "")
        shutil.make_archive(zip_base_path, 'zip', temp_dir)

        # Flush write
        zip_file_path = f"{zip_base_path}.zip"
        if os.path.exists(zip_file_path):
            print(f"[DEBUG] ZIP berhasil dibuat di: {zip_file_path}")
        else:
            print("[ERROR] ZIP tidak ditemukan setelah dibuat.")

        return zip_file_path, downloaded



