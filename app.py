from flask import Flask, render_template, request, jsonify, redirect, g, send_file, make_response
from flask_cors import CORS
from spotify_handler import SpotifyHandler
from spotipy.oauth2 import SpotifyOAuth
import spotipy
import os
import uuid
import redis
import logging
import json
import time
from dotenv import load_dotenv

load_dotenv()

# Konfigurasi OAuth Spotify
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
SCOPE = "user-library-read playlist-read-private playlist-read-collaborative"

app = Flask(__name__)
CORS(app, supports_credentials=True)  # Allow CORS with credentials

# ✅ UPDATE: Gunakan secret key dari .env agar konsisten antar deploy
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# Initialize Redis client directly (no Flask-Session)
redis_client = redis.from_url(os.getenv("REDIS_URL"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spoticheat")

# Test Redis connection
try:
    redis_client.ping()
    logger.info("✅ Redis connection OK")
except Exception as e:
    logger.error(f"❌ Redis connection FAILED: {e}")

logger.info("🚀 Flask App is starting...")
logger.info(f"🔧 SPOTIPY_REDIRECT_URI: {REDIRECT_URI}")
logger.info(f"🔧 SPOTIPY_CLIENT_ID: {CLIENT_ID}")
logger.info(f"🔧 SPOTIPY_CLIENT_SECRET: SET")

# Custom session management
SESSION_COOKIE_NAME = 'sc_session'
SESSION_PREFIX = 'sc_sess:'
SESSION_LIFETIME = 3600  # 1 hour in seconds

def generate_session_id():
    """Generate a unique session ID"""
    return f"{uuid.uuid4().hex}"

def create_session():
    """Create a new session and return session ID"""
    session_id = generate_session_id()
    session_data = {
        'created_at': int(time.time()),
        'state': str(uuid.uuid4()),  # Create OAuth state immediately
    }
    save_session(session_id, session_data)
    return session_id

def get_session(session_id):
    """Get session data from Redis"""
    if not session_id:
        return None
    
    key = f"{SESSION_PREFIX}{session_id}"
    data = redis_client.get(key)
    
    if not data:
        return None
    
    try:
        return json.loads(data)
    except:
        return None

def save_session(session_id, data):
    """Save session data to Redis"""
    key = f"{SESSION_PREFIX}{session_id}"
    redis_client.setex(key, SESSION_LIFETIME, json.dumps(data))
    logger.debug(f"Saved session {session_id}")

def delete_session(session_id):
    """Delete a session from Redis"""
    if session_id:
        key = f"{SESSION_PREFIX}{session_id}"
        redis_client.delete(key)
        logger.info(f"Deleted session {session_id}")

def get_session_id_from_request():
    """Extract session ID from cookies"""
    return request.cookies.get(SESSION_COOKIE_NAME)

def set_session_cookie(response, session_id):
    """Set session cookie on response"""
    response.set_cookie(
        SESSION_COOKIE_NAME, 
        session_id,
        httponly=True,
        secure=True,
        samesite='Lax',
        max_age=SESSION_LIFETIME
    )
    return response

def remove_session_cookie(response):
    """Remove session cookie from response"""
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response

@app.before_request
def load_user_session():
    """Load user session before each request"""
    g.session_id = get_session_id_from_request()
    g.session = get_session(g.session_id) if g.session_id else None
    g.user = None
    g.token_info = None
    
    if g.session and 'token_info' in g.session:
        token_info = g.session['token_info']
        
        # Check if token is expired and needs refresh
        auth_manager = SpotifyOAuth(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope=SCOPE,
            cache_path=None,
        )
        
        if auth_manager.is_token_expired(token_info):
            try:
                logger.info(f"Refreshing token for user {g.session.get('user_id')}")
                token_info = auth_manager.refresh_access_token(token_info['refresh_token'])
                g.session['token_info'] = token_info
                save_session(g.session_id, g.session)
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                # Don't set token_info if refresh failed
                return
        
        # Set token info and verify user
        g.token_info = token_info
        
        try:
            sp = spotipy.Spotify(auth=token_info['access_token'])
            user = sp.current_user()
            
            # Verify user matches the session user
            if not g.session.get('user_id') or user['id'] == g.session.get('user_id'):
                g.user = user
                # Update user info if needed
                if g.session.get('user_id') != user['id']:
                    g.session['user_id'] = user['id']
                    g.session['user_name'] = user.get('display_name', user['id'])
                    save_session(g.session_id, g.session)
            else:
                # User mismatch, something is wrong
                logger.warning(f"User mismatch! Session: {g.session.get('user_id')}, API: {user['id']}")
                delete_session(g.session_id)
                g.session = None
                g.token_info = None
        except Exception as e:
            logger.error(f"Error verifying user: {e}")
            g.token_info = None


def get_handler():
    """Get a SpotifyHandler instance if user is authenticated"""
    if g.token_info:
        return SpotifyHandler(token_info=g.token_info)
    return None


@app.route('/')
def index():
    """Home page - always start with a fresh session"""
    # Delete any existing session
    if g.session_id:
        delete_session(g.session_id)
    
    # Create a new response with a fresh session
    response = make_response(render_template('index.html'))
    
    # Create new session and set cookie
    new_session_id = create_session()
    set_session_cookie(response, new_session_id)
    
    logger.info(f"Created new session: {new_session_id}")
    return response


@app.route('/login_url')
def login_url():
    """Generate Spotify OAuth URL"""
    # Ensure we have a valid session
    if not g.session:
        # Create a new session if none exists
        session_id = create_session()
        g.session = get_session(session_id)
        g.session_id = session_id
    else:
        # Update state in existing session
        g.session['state'] = str(uuid.uuid4())
        save_session(g.session_id, g.session)
    
    logger.info(f"[LOGIN] Using session: {g.session_id}")
    logger.info(f"[LOGIN] Using state: {g.session['state']}")
    
    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        state=g.session['state'],
        show_dialog=True,  # Force Spotify to ask for permission again
        open_browser=False
    )
    
    auth_url = auth_manager.get_authorize_url()
    logger.info(f"Auth URL generated: {auth_url[:50]}...")
    
    # Create response with session cookie
    response = make_response(jsonify({'url': auth_url}))
    set_session_cookie(response, g.session_id)
    
    return response


@app.route('/callback')
def callback():
    """Handle Spotify OAuth callback"""
    code = request.args.get('code')
    state = request.args.get('state')
    
    logger.info(f"[CALLBACK] Callback state: {state}")
    logger.info(f"[CALLBACK] Session ID: {g.session_id}")
    
    if not g.session:
        logger.warning("No session found during callback")
        return "Session error. Please try again.", 400
    
    logger.info(f"[CALLBACK] Session state: {g.session.get('state')}")
    
    if state != g.session.get('state'):
        logger.warning("⚠️ State mismatch detected!")
        delete_session(g.session_id)
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
        
        # Update session with new user data
        g.session['token_info'] = token_info
        g.session['user_id'] = user_id
        g.session['user_name'] = user_info.get('display_name', user_id)
        g.session['login_time'] = int(time.time())
        
        # Save updated session
        save_session(g.session_id, g.session)
        
        logger.info(f"User {user_id} successfully logged in with session {g.session_id}")
        
        # Redirect to dashboard with session cookie
        response = make_response(redirect('/dashboard'))
        set_session_cookie(response, g.session_id)
        return response
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        delete_session(g.session_id)
        return "Callback error. Please try again.", 500


@app.route('/dashboard')
def dashboard():
    """Dashboard page - requires authentication"""
    handler = get_handler()
    if not handler or not g.user:
        logger.warning("Attempt to access dashboard without valid authentication")
        return redirect('/')
    
    try:
        logger.info(f"Dashboard access - Session ID: {g.session_id}, User: {g.session.get('user_id')}")
        
        playlists = handler.get_playlists()
        logger.info(f"Retrieved {len(playlists)} playlists for user {g.user['id']}")
        
        response = make_response(render_template("dashboard.html", playlists=playlists))
        set_session_cookie(response, g.session_id)  # Refresh session cookie
        return response
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return redirect('/')


@app.route('/user_info')
def user_info():
    """Get current user information"""
    if not g.user:
        return jsonify({'logged_in': False})
    
    return jsonify({
        'logged_in': True,
        'username': g.user.get('display_name', g.user.get('id')),
        'user_id': g.user.get('id'),
        'session_id': g.session_id
    })


@app.route('/select_playlist', methods=['POST'])
def select_playlist():
    """Select a playlist to download from"""
    handler = get_handler()
    if not handler:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    playlist_name = data.get('playlist')
    handler.select_playlist(playlist_name)
    tracks = handler.get_track_list()
    
    # Remember selected playlist in session
    g.session['selected_playlist'] = playlist_name
    save_session(g.session_id, g.session)
    
    return jsonify({'tracks': tracks})


@app.route('/download', methods=['POST'])
def download():
    """Download selected tracks"""
    handler = get_handler()
    if not handler:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    selected_urls = data.get('tracks', [])
    
    try:
        zip_path, results = handler.download_selected_tracks(selected_urls)
        
        # Store download path in session
        g.session['download_path'] = zip_path
        save_session(g.session_id, g.session)
        
        return jsonify({'results': results, 'download_ready': True})
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return jsonify({'error': 'Download failed', 'details': str(e)}), 500


@app.route('/get_download')
def get_download():
    """Serve download file"""
    if not g.session:
        return "Session expired", 401
        
    path = g.session.get('download_path')
    if not path or not os.path.exists(path):
        return "File tidak ditemukan.", 404
        
    return send_file(path, as_attachment=True, download_name='spoticheat_download.zip')


@app.route('/is_logged_in')
def is_logged_in():
    """Check if user is logged in"""
    if not g.user:
        return jsonify({'logged_in': False})
        
    return jsonify({'logged_in': True, 'user': g.user.get('display_name')})


@app.route('/logout')
def logout():
    """Log out user"""
    if g.session_id:
        user_id = g.session.get('user_id')
        logger.info(f"Logging out user: {user_id} with session {g.session_id}")
        delete_session(g.session_id)
    
    # Redirect to home and remove cookie
    response = make_response(redirect('/'))
    remove_session_cookie(response)
    return response


@app.route('/post_logout')
def post_logout():
    """Page shown after Spotify logout"""
    # Ensure session is cleared
    if g.session_id:
        delete_session(g.session_id)
    
    response = make_response(render_template('post_logout.html'))
    remove_session_cookie(response)
    return response


@app.route('/force_logout_spotify')
def force_logout_spotify():
    """Force logout from Spotify"""
    if g.session_id:
        delete_session(g.session_id)
    
    response = make_response(redirect("https://accounts.spotify.com/logout?continue=https://web-production-8746d.up.railway.app/post_logout"))
    remove_session_cookie(response)
    return response


@app.route('/debug_session')
def debug_session():
    """Debug endpoint for session inspection"""
    return jsonify({
        'session_id': g.session_id,
        'session_data': g.session,
        'has_user': g.user is not None,
        'user_id': g.user['id'] if g.user else None
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)