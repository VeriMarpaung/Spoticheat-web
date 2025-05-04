from spotdl import Spotdl
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import subprocess
import os
import sys
import tempfile
import shutil
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger("spoticheat")

class SpotifyHandler:
    def __init__(self, token_info=None):
        self.client_id = os.getenv("SPOTIPY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")
        self.scope = "user-library-read playlist-read-private playlist-read-collaborative"
        self.selected_playlist = None
        self.tracks = []

        self.auth_manager = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope,
            cache_path=None,
            show_dialog=True,
            open_browser=False
        )

        if token_info:
            self.sp = Spotify(auth=token_info['access_token'])
            # Verify the token works by getting current user
            try:
                self.current_user = self.sp.current_user()
                logger.info(f"SpotifyHandler initialized for user: {self.current_user['id']}")
            except Exception as e:
                logger.error(f"Token verification failed: {e}")
                self.sp = None
        else:
            self.sp = None
            logger.warning("SpotifyHandler initialized without token")

    def get_auth_url(self):
        return self.auth_manager.get_authorize_url()

    def get_playlists(self):
        if not self.sp:
            logger.error("Cannot get playlists: No valid Spotify client")
            return []
            
        try:
            playlists = self.sp.current_user_playlists()['items']
            playlist_names = [p['name'] for p in playlists]
            logger.info(f"Retrieved {len(playlist_names)} playlists")
            return playlist_names
        except Exception as e:
            logger.error(f"Error retrieving playlists: {e}")
            return []

    def select_playlist(self, name):
        if not self.sp:
            logger.error("Cannot select playlist: No valid Spotify client")
            return False
            
        try:
            playlists = self.sp.current_user_playlists()['items']
            for p in playlists:
                if p['name'] == name:
                    self.selected_playlist = p['id']
                    logger.info(f"Selected playlist: {name} (ID: {self.selected_playlist})")
                    return True
            logger.warning(f"Playlist not found: {name}")
            return False
        except Exception as e:
            logger.error(f"Error selecting playlist: {e}")
            return False

    def get_track_list(self):
        if not self.sp or not self.selected_playlist:
            logger.error("Cannot get track list: No client or playlist selected")
            return []
            
        try:
            results = self.sp.playlist_tracks(self.selected_playlist)
            self.tracks = []
            
            for item in results['items']:
                track = item.get('track')
                if not track:
                    continue
                
                # Handle potential null values
                track_name = track.get('name', 'Unknown Track')
                artist_name = 'Unknown Artist'
                if track.get('artists') and len(track['artists']) > 0:
                    artist_name = track['artists'][0].get('name', 'Unknown Artist')
                
                track_url = track.get('external_urls', {}).get('spotify', '')
                
                self.tracks.append({
                    'name': track_name,
                    'artist': artist_name,
                    'url': track_url
                })
                
            logger.info(f"Retrieved {len(self.tracks)} tracks from playlist")
            return self.tracks
        except Exception as e:
            logger.error(f"Error retrieving tracks: {e}")
            return []

    def download_selected_tracks(self, selected_urls):
        temp_dir = tempfile.mkdtemp()
        downloaded = []
        
        logger.info(f"Downloading {len(selected_urls)} tracks to {temp_dir}")
        
        for url in selected_urls:
            logger.info(f"Downloading: {url}")
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
                    logger.info(f"Successfully downloaded: {url}")
                else:
                    downloaded.append(f"Failed: {url} (non-zero exit)")
                    logger.warning(f"Download failed with non-zero exit: {url}")
            except subprocess.TimeoutExpired:
                downloaded.append(f"Timeout: {url}")
                logger.warning(f"Download timed out: {url}")
            except Exception as e:
                downloaded.append(f"Error: {url} - {str(e)}")
                logger.error(f"Download error: {url} - {str(e)}")

        zip_path = Path(temp_dir).parent / "songs_downloaded.zip"
        shutil.make_archive(str(zip_path).replace(".zip", ""), 'zip', temp_dir)
        logger.info(f"Created zip archive at {zip_path}")

        # Bersihkan folder temp setelah ZIP dibuat
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"Cleaned up temporary directory {temp_dir}")

        return str(zip_path), downloaded