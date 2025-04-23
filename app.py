from flask import Flask, render_template, request, jsonify, session, redirect, g, send_file
from flask_session import Session
from flask_cors import CORS
from spotify_handler import SpotifyHandler
from spotipy.oauth2 import SpotifyOAuth
import spotipy
import os
import uuid
import redis
import logging
from dotenv import load_dotenv

load_dotenv()

# Konfigurasi OAuth Spotify
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
SCOPE = "user-library-read playlist-read-private playlist-read-collaborative"

app = Flask(__name__)
CORS(app, supports_credentials=True)  # Jika menggunakan frontend JS

# ✅ UPDATE: Gunakan secret key dari .env agar konsisten antar deploy
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# Konfigurasi Redis untuk sesi
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url(os.getenv("REDIS_URL"))
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'spoticheat_'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_DOMAIN'] = '.railway.app'  # ✅ Tambahan penting agar cookie berlaku lintas subdomain

Session(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spoticheat")

# ✅ TEST Redis connection
try:
    app.config['SESSION_REDIS'].ping()
    logger.info("✅ Redis connection OK")
except Exception as e:
    logger.error(f"❌ Redis connection FAILED: {e}")

logger.info("🚀 Flask App is starting...")
logger.info(f"🔧 SPOTIPY_REDIRECT_URI: {REDIRECT_URI}")
logger.info(f"🔧 SPOTIPY_CLIENT_ID: {CLIENT_ID}")
logger.info(f"🔧 SPOTIPY_CLIENT_SECRET: SET")


def refresh_token_if_needed():
    token_info = session.get('token_info')
    if not token_info:
        return None

    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=None,
    )

    if auth_manager.is_token_expired(token_info):
        try:
            token_info = auth_manager.refresh_access_token(token_info['refresh_token'])
            session['token_info'] = token_info
            session.modified = True
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            session.clear()
            return None

    return token_info


@app.before_request
def load_token_info():
    g.token_info = refresh_token_if_needed()


def get_handler():
    if g.get('token_info'):
        return SpotifyHandler(token_info=g.token_info)
    return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login_url')
def login_url():
    session.clear()
    state = str(uuid.uuid4())
    session['state'] = state
    logger.info(f"[LOGIN] Generated session state: {session['state']}")  # ✅ Log state untuk debugging

    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        state=session['state'],
        show_dialog=True,
        open_browser=False
    )
    auth_url = auth_manager.get_authorize_url()
    return jsonify({'url': auth_url})

@app.route('/callback')
def callback():
    code = request.args.get('code')
    state = request.args.get('state')

    # ✅ DEBUG: Log session dan callback state
    logger.info(f"[CALLBACK] Callback state: {state}")
    logger.info(f"[CALLBACK] Session state: {session.get('state')}")

    if state != session.get('state'):
        logger.warning("⚠️ State mismatch detected!")
        return "State mismatch. Authentication failed.", 403

    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=None,
    )

    try:
        token_info = auth_manager.get_access_token(code, as_dict=True)
        sp = spotipy.Spotify(auth=token_info['access_token'])
        user_id = sp.current_user()['id']

        session['token_info'] = token_info
        session['user_id'] = user_id
        session.modified = True

        return redirect('/dashboard')
    except Exception as e:
        logger.error(f"Callback error: {e}")
        return "Callback error", 500


@app.route('/dashboard')
def dashboard():
    handler = get_handler()
    if not handler:
        return redirect('/')

    try:
        me = handler.sp.current_user()
        if me['id'] != session.get('user_id'):
            session.clear()
            return redirect('/')

        playlists = handler.get_playlists()
        return render_template("dashboard.html", playlists=playlists)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        session.clear()
        return redirect('/')


@app.route('/select_playlist', methods=['POST'])
def select_playlist():
    handler = get_handler()
    if not handler:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    playlist_name = data.get('playlist')
    handler.select_playlist(playlist_name)
    tracks = handler.get_track_list()
    return jsonify({'tracks': tracks})


@app.route('/download', methods=['POST'])
def download():
    handler = get_handler()
    if not handler:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    selected_urls = data.get('tracks', [])

    try:
        zip_path, results = handler.download_selected_tracks(selected_urls)
        session['download_path'] = zip_path
        session.modified = True
        return jsonify({'results': results, 'download_ready': True})
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return jsonify({'error': 'Download failed', 'details': str(e)}), 500


@app.route('/get_download')
def get_download():
    path = session.get('download_path')
    if not path or not os.path.exists(path):
        return "File tidak ditemukan.", 404
    return send_file(path, as_attachment=True, download_name='spoticheat_download.zip')


@app.route('/is_logged_in')
def is_logged_in():
    handler = get_handler()
    if not handler:
        return jsonify({'logged_in': False})
    try:
        user = handler.sp.current_user()
        return jsonify({'logged_in': True, 'user': user['display_name']})
    except:
        return jsonify({'logged_in': False})


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/post_logout')
def post_logout():
    return render_template('post_logout.html')


@app.route('/force_logout_spotify')
def force_logout_spotify():
    session.clear()
    return redirect("https://accounts.spotify.com/logout?continue=https://web-production-8746d.up.railway.app/post_logout")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
