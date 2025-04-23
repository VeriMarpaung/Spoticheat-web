# from flask import Flask, render_template, request, jsonify, session, redirect, g  # <--- tambahkan g
# from flask import send_file
# from spotify_handler import SpotifyHandler
# from spotipy.oauth2 import SpotifyOAuth
# import threading
# import uuid
# import os
# from dotenv import load_dotenv
# load_dotenv()
# import logging

# # Konfigurasi utama
# CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
# CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
# REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
# SCOPE = "user-library-read playlist-read-private playlist-read-collaborative"

# app = Flask(__name__)
# app.secret_key = CLIENT_SECRET  # Untuk session

# # Logging untuk debug Railway
# logging.basicConfig(level=logging.DEBUG)
# print("🚀 Flask App is starting...")
# print(f"🔧 SPOTIPY_CLIENT_ID: {CLIENT_ID}")
# print(f"🔧 SPOTIPY_CLIENT_SECRET: {'SET' if CLIENT_SECRET else 'NOT SET'}")
# print(f"🔧 SPOTIPY_REDIRECT_URI: {REDIRECT_URI}")


# def refresh_token_if_needed():
#     """Refresh token jika sudah expired, dan set ke session lagi"""
#     token_info = session.get('token_info')
#     if not token_info:
#         return None

#     auth_manager = SpotifyOAuth(
#         client_id=CLIENT_ID,
#         client_secret=CLIENT_SECRET,
#         redirect_uri=REDIRECT_URI,
#         scope=SCOPE,
#         cache_path=None,
#     )

#     if auth_manager.is_token_expired(token_info):
#         token_info = auth_manager.refresh_access_token(token_info['refresh_token'])
#         session['token_info'] = token_info

#     return token_info


# @app.before_request
# def load_token_info():
#     """Hook global sebelum request, set g.token_info kalau tersedia"""
#     token_info = refresh_token_if_needed()
#     g.token_info = token_info  # Simpan ke context global Flask


# # Helper untuk inisialisasi handler dengan token user
# def get_handler():
#     if g.get('token_info'):
#         return SpotifyHandler(token_info=g.token_info)
#     return None




# @app.route('/')
# def index():
#     return render_template('index.html')


# @app.route('/login_url')
# def login_url():
#     session.clear()
#     session['state'] = str(uuid.uuid4())  # state unik
#     auth_manager = SpotifyOAuth(
#         client_id=CLIENT_ID,
#         client_secret=CLIENT_SECRET,
#         redirect_uri=REDIRECT_URI,
#         scope=SCOPE,
#         state=session['state'],
#         show_dialog=True,
#         open_browser=False
#     )
#     auth_url = auth_manager.get_authorize_url()
#     return jsonify({'url': auth_url})


# @app.route('/callback')
# def callback():
#     code = request.args.get('code')
#     state = request.args.get('state')

#     if state != session.get('state'):
#         return "State mismatch. Authentication failed.", 403

#     auth_manager = SpotifyOAuth(
#         client_id=CLIENT_ID,
#         client_secret=CLIENT_SECRET,
#         redirect_uri=REDIRECT_URI,
#         scope=SCOPE,
#         cache_path=None,
#     )

#     token_info = auth_manager.get_access_token(code, as_dict=True)
    
#     # ✅ Gunakan token untuk ambil ID user
#     import spotipy
#     sp = spotipy.Spotify(auth=token_info['access_token'])
#     user_id = sp.current_user()['id']

#     # 💾 Simpan cache path sesuai user
#     session['token_info'] = token_info
#     session['user_id'] = user_id  # simpan juga ID user

#     return redirect('/dashboard')


# @app.route('/dashboard')
# def dashboard():
#     handler = get_handler()
#     if not handler:
#         return redirect('/')

#     me = handler.sp.current_user()
#     print(f"[DEBUG] Logged in as: {me['display_name']} ({me['id']})")  # Debug siapa yang login

#     playlists = handler.get_playlists()
#     return render_template("dashboard.html", playlists=playlists)



# @app.route('/select_playlist', methods=['POST'])
# def select_playlist():
#     handler = get_handler()
#     if not handler:
#         return jsonify({'error': 'Not logged in'}), 401

#     data = request.get_json()
#     playlist_name = data.get('playlist')
#     handler.select_playlist(playlist_name)
#     tracks = handler.get_track_list()
#     return jsonify({'tracks': tracks})


# @app.route('/download', methods=['POST'])
# def download():
#     handler = get_handler()
#     if not handler:
#         return jsonify({'error': 'Not logged in'}), 401

#     data = request.get_json()
#     selected_urls = data.get('tracks', [])

#     try:
#         zip_path, results = handler.download_selected_tracks(selected_urls)
#         session['download_path'] = zip_path  # Simpan ke session agar bisa diakses di /get_download

#         return jsonify({'results': results, 'download_ready': True})
    
#     except Exception as e:
#         # Log error ke server dan kirim respons error ke klien
#         print(f"[ERROR] Download failed: {e}")
#         return jsonify({'error': 'Download failed', 'details': str(e)}), 500


# @app.route('/get_download')
# def get_download():
#     path = session.get('download_path')
#     if not path or not os.path.exists(path):
#         return "File tidak ditemukan.", 404
#     return send_file(path, as_attachment=True, download_name='spoticheat_download.zip')


# @app.route('/is_logged_in')
# def is_logged_in():
#     handler = get_handler()
#     if not handler:
#         return jsonify({'logged_in': False})
#     try:
#         user = handler.sp.current_user()
#         return jsonify({'logged_in': True, 'user': user['display_name']})
#     except:
#         return jsonify({'logged_in': False})


# @app.route('/logout')
# def logout():
#     session.clear()
#     return redirect('/')

# @app.route('/post_logout')
# def post_logout():
#     return render_template('post_logout.html')  # halaman dengan tombol atau auto-redirect




from flask import Flask, render_template, request, jsonify, session, redirect, g, send_file
from flask_session import Session
from spotify_handler import SpotifyHandler
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import uuid
import os
import spotipy
import redis
import logging

load_dotenv()

# Konfigurasi utama
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
SCOPE = "user-library-read playlist-read-private playlist-read-collaborative"

app = Flask(__name__)
app.secret_key = CLIENT_SECRET

# 🔧 Konfigurasi Redis yang benar
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url("redis://default:PvhBBpsuCMXpPtapzuOnhlHAsqtHEJGm@redis.railway.internal:6379")
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'spoticheat_'
Session(app)

logging.basicConfig(level=logging.DEBUG)
print("🚀 Flask App is starting...")
print(f"🔧 SPOTIPY_CLIENT_ID: {CLIENT_ID}")
print(f"🔧 SPOTIPY_CLIENT_SECRET: {'SET' if CLIENT_SECRET else 'NOT SET'}")
print(f"🔧 SPOTIPY_REDIRECT_URI: {REDIRECT_URI}")


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
        token_info = auth_manager.refresh_access_token(token_info['refresh_token'])
        session['token_info'] = token_info
        session.modified = True  # 🔁 agar session tersimpan ulang

    return token_info


@app.before_request
def load_token_info():
    token_info = refresh_token_if_needed()
    g.token_info = token_info


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
    session['state'] = str(uuid.uuid4())
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

    if state != session.get('state'):
        return "State mismatch. Authentication failed.", 403

    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=None,
    )

    token_info = auth_manager.get_access_token(code, as_dict=True)
    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_id = sp.current_user()['id']

    session['token_info'] = token_info
    session['user_id'] = user_id
    session.modified = True  # ✅ pastikan session tersimpan di Redis

    return redirect('/dashboard')


@app.route('/dashboard')
def dashboard():
    handler = get_handler()
    if not handler:
        return redirect('/')

    me = handler.sp.current_user()
    print(f"[DEBUG] Logged in as: {me['display_name']} ({me['id']})")

    # 🔒 Validasi: user session dan user token harus sama
    if me['id'] != session.get('user_id'):
        print("[WARNING] User ID in session does not match current user")
        session.clear()
        return redirect('/')

    playlists = handler.get_playlists()
    return render_template("dashboard.html", playlists=playlists)


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
        print(f"[ERROR] Download failed: {e}")
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
    port = int(os.environ.get('PORT', 5000))  # 5000 buat local default
    app.run(debug=False, host='0.0.0.0', port=port)