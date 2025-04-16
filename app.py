from flask import Flask, render_template, request, jsonify, session, redirect
from flask import send_file
from spotify_handler import SpotifyHandler
from spotipy.oauth2 import SpotifyOAuth
import threading
import os

# Konfigurasi utama
CLIENT_ID = "7d145b84e88c40e680bfe54a2f47d651"
CLIENT_SECRET = "25d72c96fb0f4013a2e3d70e9add7c28"
# REDIRECT_URI = "https://verim.pythonanywhere.com/callback"
REDIRECT_URI = "http://127.0.0.1:5000/callback"
SCOPE = "user-library-read playlist-read-private playlist-read-collaborative"

app = Flask(__name__)
app.secret_key = CLIENT_SECRET  # Untuk session

# Helper untuk inisialisasi handler dengan token user
def get_handler():
    token_info = session.get('token_info')
    if token_info:
        return SpotifyHandler(token_info=token_info)
    return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login_url')
def login_url():
    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=".cache-web",
        show_dialog=True,
        open_browser=False
    )
    return jsonify({'url': auth_manager.get_authorize_url()})


@app.route('/callback')
def callback():
    code = request.args.get('code')
    if code:
        auth_manager = SpotifyOAuth(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope=SCOPE,
            cache_path=".cache-web"
        )
        token_info = auth_manager.get_access_token(code, as_dict=True)
        session['token_info'] = token_info
        return redirect('/dashboard')
    else:
        return "Authorization failed.", 400


@app.route('/dashboard')
def dashboard():
    handler = get_handler()
    if not handler:
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


# @app.route('/download', methods=['POST'])
# def download():
#     handler = get_handler()
#     if not handler:
#         return jsonify({'error': 'Not logged in'}), 401

#     data = request.get_json()
#     selected_urls = data.get('tracks', [])
#     results = []

#     def _download():
#         nonlocal results
#         results.extend(handler.download_selected_tracks(selected_urls))

#     thread = threading.Thread(target=_download)
#     thread.start()
#     thread.join()

#     return jsonify({'results': results})

@app.route('/download', methods=['POST'])
def download():
    handler = get_handler()
    if not handler:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    selected_urls = data.get('tracks', [])

    zip_path, results = handler.download_selected_tracks(selected_urls)

    session['download_path'] = zip_path  # Simpan ke session agar bisa diakses di /get_download

    return jsonify({'results': results, 'download_ready': True})

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


if __name__ == '__main__':
    app.run(debug=True)
