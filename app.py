import os
import sqlite3
import uuid
import threading
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for React Native/Expo requests

DB_FILE = 'map_data.db'

# Thread-safe global cache variables
CACHE_API_KEYS = set()
CACHE_MARKERS = []
CACHE_CONFIG = {}
CACHE_LOCK = threading.Lock()

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Create markers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS markers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            title TEXT,
            description TEXT,
            created_at TEXT
        )
    ''')
    
    # Create api_keys table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            key TEXT PRIMARY KEY,
            description TEXT,
            created_at TEXT
        )
    ''')
    
    # Create map_buttons configuration table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS map_buttons (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            action_type TEXT NOT NULL,  -- 'style' or 'function'
            map_type TEXT NOT NULL,     -- 'standard' or 'hybrid'
            pitch INTEGER NOT NULL,     -- 0 to 90
            buildings INTEGER NOT NULL, -- 0 or 1
            enabled INTEGER NOT NULL    -- 0 or 1
        )
    ''')
    
    # Pre-populate sample markers if empty
    cursor.execute("SELECT COUNT(*) FROM markers")
    if cursor.fetchone()[0] == 0:
        sample_markers = [
            (41.0082, 28.9784, 'Istanbul', '12 photos here', datetime.now().isoformat()),
            (39.9334, 32.8597, 'Ankara', '5 photos here', datetime.now().isoformat()),
            (38.4192, 27.1287, 'Izmir', '8 photos here', datetime.now().isoformat())
        ]
        cursor.executemany(
            "INSERT INTO markers (latitude, longitude, title, description, created_at) VALUES (?, ?, ?, ?, ?)",
            sample_markers
        )
        
    # Pre-populate default API key if empty
    cursor.execute("SELECT COUNT(*) FROM api_keys")
    if cursor.fetchone()[0] == 0:
        default_key = "iz-app-default-secret-key-2026"
        cursor.execute(
            "INSERT INTO api_keys (key, description, created_at) VALUES (?, ?, ?)",
            (default_key, "Default Key for Expo Mobile Client", datetime.now().isoformat())
        )
        print(f"--> Initialized database. Default API Key: {default_key}")

    # Pre-populate map buttons if empty
    cursor.execute("SELECT COUNT(*) FROM map_buttons")
    if cursor.fetchone()[0] == 0:
        default_buttons = [
            ('2d', '2D Harita', 'style', 'standard', 0, 0, 1),
            ('3d', '3D Görünüm', 'style', 'standard', 65, 1, 1),
            ('detail', 'Detaylı Uydu', 'style', 'hybrid', 45, 1, 1),
            ('locate', 'Konumumu Bul', 'function', 'standard', 0, 0, 1)
        ]
        cursor.executemany(
            "INSERT INTO map_buttons (id, label, action_type, map_type, pitch, buildings, enabled) VALUES (?, ?, ?, ?, ?, ?, ?)",
            default_buttons
        )

    conn.commit()
    conn.close()

# Reload everything from SQLite database into memory cache
def load_cache():
    global CACHE_API_KEYS, CACHE_MARKERS, CACHE_CONFIG
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Load active API keys
    cursor.execute("SELECT key FROM api_keys")
    keys_rows = cursor.fetchall()
    keys_set = {row["key"] for row in keys_rows}
    
    # 2. Load markers
    cursor.execute("SELECT id, latitude, longitude, title, description FROM markers")
    marker_rows = cursor.fetchall()
    markers_list = []
    for row in marker_rows:
        markers_list.append({
            "coordinate": {
                "latitude": row["latitude"],
                "longitude": row["longitude"]
            },
            "title": row["title"],
            "description": row["description"]
        })
        
    # 3. Load map buttons config (only enabled ones for CACHE_CONFIG)
    cursor.execute("SELECT id, label, action_type, map_type, pitch, buildings FROM map_buttons WHERE enabled = 1")
    buttons_rows = cursor.fetchall()
    buttons_list = []
    for row in buttons_rows:
        buttons_list.append({
            "id": row["id"],
            "label": row["label"],
            "action_type": row["action_type"],
            "map_type": row["map_type"],
            "pitch": row["pitch"],
            "buildings": bool(row["buildings"])
        })
        
    conn.close()
    
    # Update cache atomically
    with CACHE_LOCK:
        CACHE_API_KEYS = keys_set
        CACHE_MARKERS = markers_list
        CACHE_CONFIG = {
            "default_region": {
                "latitude": 39.9334,
                "longitude": 32.8597,
                "latitudeDelta": 10,
                "longitudeDelta": 10,
            },
            "default_view_mode": "2d",
            "map_buttons": buttons_list
        }
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Cache successfully updated in memory.")

# Helper to validate API keys from in-memory cache directly (sub-microsecond speed)
def require_api_key(f):
    def decorator(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({"error": "Missing API Key"}), 401
        
        # Lockless read from cache set
        if api_key not in CACHE_API_KEYS:
            return jsonify({"error": "Invalid API Key"}), 403
            
        return f(*args, **kwargs)
    decorator.__name__ = f.__name__
    return decorator

@app.route('/')
def index():
    return render_template('index.html')

# ADMIN API: Get all markers
@app.route('/admin/markers', methods=['GET'])
def admin_get_markers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM markers ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

# ADMIN API: Add marker
@app.route('/admin/markers', methods=['POST'])
def admin_add_marker():
    data = request.json
    lat = data.get('latitude')
    lng = data.get('longitude')
    title = data.get('title', 'New Location')
    desc = data.get('description', '')
    
    if lat is None or lng is None:
        return jsonify({"error": "Latitude and longitude are required"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO markers (latitude, longitude, title, description, created_at) VALUES (?, ?, ?, ?, ?)",
        (lat, lng, title, desc, datetime.now().isoformat())
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    
    # Sync cache
    load_cache()
    return jsonify({"success": True, "id": new_id})

# ADMIN API: Delete marker
@app.route('/admin/markers/<int:marker_id>', methods=['DELETE'])
def admin_delete_marker(marker_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM markers WHERE id = ?", (marker_id,))
    conn.commit()
    conn.close()
    
    # Sync cache
    load_cache()
    return jsonify({"success": True})

# ADMIN API: Get API Keys
@app.route('/admin/api-keys', methods=['GET'])
def admin_get_keys():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

# ADMIN API: Generate API Key
@app.route('/admin/api-keys', methods=['POST'])
def admin_generate_key():
    data = request.json or {}
    desc = data.get('description', 'Manual Key')
    new_key = "iz_" + uuid.uuid4().hex
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO api_keys (key, description, created_at) VALUES (?, ?, ?)",
        (new_key, desc, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
    # Sync cache
    load_cache()
    return jsonify({"success": True, "key": new_key})

# ADMIN API: Revoke/Delete API Key
@app.route('/admin/api-keys/<string:key>', methods=['DELETE'])
def admin_delete_key(key):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    
    # Sync cache
    load_cache()
    return jsonify({"success": True})

# ADMIN API: Get Map Buttons
@app.route('/admin/map-buttons', methods=['GET'])
def admin_get_map_buttons():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM map_buttons")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

# ADMIN API: Update Map Button
@app.route('/admin/map-buttons/<string:button_id>', methods=['POST'])
def admin_update_map_button(button_id):
    data = request.json
    label = data.get('label')
    action_type = data.get('action_type')
    map_type = data.get('map_type')
    pitch = data.get('pitch')
    buildings = data.get('buildings')
    enabled = data.get('enabled')
    
    if label is None or action_type is None or map_type is None or pitch is None or buildings is None or enabled is None:
        return jsonify({"error": "All fields are required"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE map_buttons SET label = ?, action_type = ?, map_type = ?, pitch = ?, buildings = ?, enabled = ? WHERE id = ?",
        (label, action_type, map_type, int(pitch), int(buildings), int(enabled), button_id)
    )
    conn.commit()
    conn.close()
    
    # Sync cache
    load_cache()
    return jsonify({"success": True})

# ADMIN API: Add Custom Map Button
@app.route('/admin/map-buttons', methods=['POST'])
def admin_add_map_button():
    data = request.json
    label = data.get('label')
    action_type = data.get('action_type', 'style')
    map_type = data.get('map_type', 'standard')
    pitch = data.get('pitch', 0)
    buildings = data.get('buildings', 0)
    enabled = data.get('enabled', 1)
    
    if not label:
        return jsonify({"error": "Label is required"}), 400
        
    # Generate unique ID
    button_id = "btn_" + uuid.uuid4().hex[:8]
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO map_buttons (id, label, action_type, map_type, pitch, buildings, enabled) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (button_id, label, action_type, map_type, int(pitch), int(buildings), int(enabled))
    )
    conn.commit()
    conn.close()
    
    # Sync cache
    load_cache()
    return jsonify({"success": True, "id": button_id})

# ADMIN API: Delete Custom Map Button
@app.route('/admin/map-buttons/<string:button_id>', methods=['DELETE'])
def admin_delete_map_button(button_id):
    # Don't delete system default buttons, just disable them
    system_buttons = ['2d', '3d', 'detail', 'locate']
    conn = get_db()
    cursor = conn.cursor()
    if button_id in system_buttons:
        cursor.execute("UPDATE map_buttons SET enabled = 0 WHERE id = ?", (button_id,))
    else:
        cursor.execute("DELETE FROM map_buttons WHERE id = ?", (button_id,))
    conn.commit()
    conn.close()
    
    # Sync cache
    load_cache()
    return jsonify({"success": True})


# MOBILE APP API: Get Config (Cached, sub-millisecond)
@app.route('/api/config', methods=['GET'])
@require_api_key
def get_config():
    return jsonify(CACHE_CONFIG)

# MOBILE APP API: Get Markers (Cached, sub-millisecond)
@app.route('/api/markers', methods=['GET'])
@require_api_key
def get_markers():
    return jsonify(CACHE_MARKERS)

# High-Performance Performance Test / Health Check Endpoint
@app.route('/api/health-check', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "cached_keys_count": len(CACHE_API_KEYS),
        "cached_markers_count": len(CACHE_MARKERS),
        "timestamp": datetime.now().isoformat()
    })

# MOBILE APP WEBVIEW MAP: Renders a clean full-screen map verified by API key query param
@app.route('/map', methods=['GET'])
def render_webview_map():
    api_key = request.args.get('key')
    if not api_key or api_key not in CACHE_API_KEYS:
        return "Unauthorized: Invalid or missing API Key", 403
    return render_template('map_view.html', api_key=api_key)

# Initialize Database and Load Cache on load
init_db()
load_cache()

if __name__ == '__main__':
    # Listen on all interfaces so the phone can connect
    app.run(host='0.0.0.0', port=3000, debug=True)
