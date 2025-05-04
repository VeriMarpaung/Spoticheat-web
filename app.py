from flask import Flask, render_template, request, jsonify, session, redirect, g, send_file, make_response
from flask_session import Session
from flask_cors import CORS
from spotify_handler import SpotifyHandler
from spotipy.oauth2 import SpotifyOAuth
import spotipy
import os
import uuid
import redis
import logging
import time
from dotenv import load_dotenv

load_dotenv()

# Konfigurasi OAuth Spotify
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
SCOPE = "user-library-read playlist-read-private playlist-read-collaborative"

app = Flask(__name__)
CORS(app, supports_credentials=True)

# ✅ UPDATE: Gunakan secret key dari .env agar konsisten antar deploy
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# Konfigurasi Redis untuk sesi - with more aggressive session management
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url(os.getenv("REDIS_URL"))
app.config['SESSION_PERMANENT'] = False  # Changed to False to expire after browser close
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'spoticheat_'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # Session expires after 1 hour

# Memperbaiki konfigurasi cookie untuk session
app.config['SESSION_COOKIE_NAME'] = 'spoticheat_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Changed from 'None' to 'Lax' for better security
app.config['SESSION_COOKIE_SECURE'] = True

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

# Utility function to generate a unique session ID
def generate_session_id():
    return f"session_{uuid.uuid4().hex}"

def refresh_token_if_needed():
    token_info = session.get('token_info')
    if not token_info:
        logger.info("No token_info in session")
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
            logger.info(f"Refreshing token for user {session.get('user_id')}")
            token_info = auth_manager.refresh_access_token(token_info['refresh_token'])
            session['token_info'] = token_info
            session.modified = True
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            clear_session()
            return None

    return token_info

# Function to properly clear all session data
def clear_session():
    # Get the session ID if it exists
    if session.sid:
        try:
            # Try to delete the session from Redis directly
            app.config['SESSION_REDIS'].delete(f"{app.config['SESSION_KEY_PREFIX']}{session.sid}")
            logger.info(f"Deleted session {session.sid} from Redis")
        except Exception as e:
            logger.error(f"Failed to delete session from Redis: {e}")
    
    # Clear the Flask session
    session.clear()
    logger.info("Session cleared")

@app.before_request
def load_token_info():
    # Log every request for debugging
    logger.debug(f"Request path: {request.path}")
    logger.debug(f"Session ID: {session.get('_id')}")
    logger.debug(f"Session User ID: {session.get('user_id')}")
    
    try:
        g.token_info = refresh_token_if_needed()
        
        # Verify token matches current user
        if g.token_info and 'access_token' in g.token_info:
            try:
                sp = spotipy.Spotify(auth=g.token_info['access_token'])
                current_user = sp.current_user()
                
                if current_user['id'] != session.get('user_id'):
                    logger.warning(f"Session user mismatch! Session: {session.get('user_id')}, Token: {current_user['id']}")
                    clear_session()
                    g.token_info = None
                else:
                    logger.debug(f"User verified: {current_user['id']}")
            except Exception as e:
                logger.error(f"Token verification error: {e}")
                clear_session()
                g.token_info = None
    except Exception as e:
        logger.error(f"Error in before_request: {e}")
        g.token_info = None


def get_handler():
    if g.get('token_info'):
        return SpotifyHandler(token_info=g.token_info)
    return None


@app.route('/')
def index():
    # Force clear session when hitting the index page
    clear_session()
    # Create a new session with a unique ID
    session['_id'] = generate_session_id()
    session.modified = True
    
    logger.info(f"New session created: {session.get('_id')}")
    return render_template('index.html')


@app.route('/login_url')
def login_url():
    # Ensure we have a clean session
    clear_session()
    
    # Create new session with unique identifiers
    session['_id'] = generate_session_id()
    state = str(uuid.uuid4())
    session['state'] = state
    session['login_time'] = int(time.time())
    session.modified = True
    
    logger.info(f"[LOGIN] New session ID: {session.get('_id')}")
    logger.info(f"[LOGIN] Generated session state: {state}")
    
    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        state=state,
        show_dialog=True,  # Force Spotify to ask for permission again
        open_browser=False
    )
    auth_url = auth_manager.get_authorize_url()
    logger.info(f"Auth URL generated: {auth_url[:50]}...")
    
    response = jsonify({'url': auth_url})
    return response


@app.route('/callback')
def callback():
    code = request.args.get('code')
    state = request.args.get('state')

    logger.info(f"[CALLBACK] Callback state: {state}")
    logger.info(f"[CALLBACK] Session state: {session.get('state')}")
    logger.info(f"[CALLBACK] Session ID: {session.get('_id')}")

    if state != session.get('state'):
        logger.warning("⚠️ State mismatch detected!")
        clear_session()
        return "State mismatch. Authentication failed. Please try again.", 403

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
        user_info = sp.current_user()
        user_id = user_info['id']

        # Keep the session ID but clear other data
        session_id = session.get('_id')
        clear_session()
        
        # Set fresh session data
        session['_id'] = session_id
        session['token_info'] = token_info
        session['user_id'] = user_id
        session['user_name'] = user_info.get('display_name', user_id)
        session['login_time'] = int(time.time())
        session.modified = True
        
        logger.info(f"User {user_id} successfully logged in with session {session_id}")

        return redirect('/dashboard')
    except Exception as e:
        logger.error(f"Callback error: {e}")
        clear_session()
        return "Callback error. Please try again.", 500


@app.route('/dashboard')
def dashboard():
    handler = get_handler()
    if not handler:
        logger.warning("Attempt to access dashboard without valid handler")
        return redirect('/')

    try:
        me = handler.sp.current_user()
        if me['id'] != session.get('user_id'):
            logger.warning(f"User ID mismatch: {me['id']} vs {session.get('user_id')}")
            clear_session()
            return redirect('/')

        # Log complete session data for debugging
        logger.info(f"Dashboard access - Session ID: {session.get('_id')}, User: {session.get('user_id')}")
        
        playlists = handler.get_playlists()
        logger.info(f"Retrieved {len(playlists)} playlists for user {me['id']}")
        return render_template("dashboard.html", playlists=playlists)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        clear_session()
        return redirect('/')


@app.route('/user_info')
def user_info():
    handler = get_handler()
    if not handler:
        return jsonify({'logged_in': False})
    try:
        user = handler.sp.current_user()
        if user['id'] != session.get('user_id'):
            logger.warning(f"User ID mismatch in user_info: {user['id']} vs {session.get('user_id')}")
            clear_session()
            return jsonify({'logged_in': False})
            
        return jsonify({
            'logged_in': True, 
            'username': user.get('display_name', user.get('id')),
            'user_id': user.get('id'),
            'session_id': session.get('_id')
        })
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        clear_session()
        return jsonify({'logged_in': False})


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
        # Verify user ID matches session
        if user['id'] != session.get('user_id'):
            logger.warning(f"User ID mismatch in is_logged_in: {user['id']} vs {session.get('user_id')}")
            clear_session()
            return jsonify({'logged_in': False})
        return jsonify({'logged_in': True, 'user': user['display_name']})
    except Exception as e:
        logger.error(f"Error in is_logged_in: {e}")
        clear_session()
        return jsonify({'logged_in': False})


@app.route('/logout')
def logout():
    # Get user ID for logging
    user_id = session.get('user_id')
    logger.info(f"Logging out user: {user_id} with session {session.get('_id')}")
    
    # Clear all session data
    clear_session()
    
    # Create response with redirect
    return redirect('/')


@app.route('/post_logout')
def post_logout():
    # Ensure session is cleared here too
    clear_session()
    return render_template('post_logout.html')


@app.route('/force_logout_spotify')
def force_logout_spotify():
    clear_session()
    
    # Mengarahkan ke halaman logout Spotify kemudian kembali ke post_logout
    return redirect("https://accounts.spotify.com/logout?continue=https://web-production-8746d.up.railway.app/post_logout")


@app.route('/debug_session')
def debug_session():
    """Debugging endpoint for session inspection - remove in production"""
    if app.config.get('DEBUG', False):
        session_data = {k: str(v) for k, v in session.items()}
        return jsonify({
            'session': session_data,
            'sid': session.sid if hasattr(session, 'sid') else None
        })
    return "Not available in production", 403


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)