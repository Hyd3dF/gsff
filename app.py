import os
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for React Native/Expo requests

DB_FILE = 'map_data.db'

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

    conn.commit()
    conn.close()

# Helper to validate API keys from headers
def require_api_key(f):
    def decorator(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({"error": "Missing API Key"}), 401
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM api_keys WHERE key = ?", (api_key,))
        key_exists = cursor.fetchone()
        conn.close()
        
        if not key_exists:
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
    
    return jsonify({"success": True, "id": new_id})

# ADMIN API: Delete marker
@app.route('/admin/markers/<int:marker_id>', methods=['DELETE'])
def admin_delete_marker(marker_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM markers WHERE id = ?", (marker_id,))
    conn.commit()
    conn.close()
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
    
    return jsonify({"success": True, "key": new_key})

# ADMIN API: Revoke/Delete API Key
@app.route('/admin/api-keys/<string:key>', methods=['DELETE'])
def admin_delete_key(key):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# MOBILE APP API: Get Config (requires API key)
@app.route('/api/config', methods=['GET'])
@require_api_key
def get_config():
    # Returns map default settings
    return jsonify({
        "default_region": {
            "latitude": 39.9334,
            "longitude": 32.8597,
            "latitudeDelta": 10,
            "longitudeDelta": 10,
        },
        "default_view_mode": "2d"
    })

# MOBILE APP API: Get Markers (requires API key)
@app.route('/api/markers', methods=['GET'])
@require_api_key
def get_markers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, latitude, longitude, title, description FROM markers")
    rows = cursor.fetchall()
    conn.close()
    
    markers = []
    for row in rows:
        markers.append({
            "coordinate": {
                "latitude": row["latitude"],
                "longitude": row["longitude"]
            },
            "title": row["title"],
            "description": row["description"]
        })
    return jsonify(markers)

if __name__ == '__main__':
    init_db()
    # Listen on all interfaces so the phone can connect
    app.run(host='0.0.0.0', port=5000, debug=True)
