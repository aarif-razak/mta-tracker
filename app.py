#!/usr/bin/env python3
"""
MTA Subway Tracker - Flask API Backend
Serves real-time train data via REST API
"""

from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import threading
import time
from datetime import datetime, timedelta, timezone
import requests
import csv
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from google.transit import gtfs_realtime_pb2

app = Flask(__name__, static_folder='static', static_url_path='')

# Security: Restrict CORS to specific origins in production
# For development, allow all. In production, set ALLOWED_ORIGINS env variable
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*')
if ALLOWED_ORIGINS == '*':
    CORS(app)
else:
    CORS(app, origins=ALLOWED_ORIGINS.split(','))

# Configuration
FEED_URLS = {
    'JZ': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
    'ACE': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
    'BDFM': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
    'G': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
    'NQRW': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    'L': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
    '1234567S': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
}
STOPS_FILE = "stops.txt"
UPDATE_INTERVAL = 10  # seconds - how often to poll MTA feeds
DATA_STALE_THRESHOLD = 60  # seconds - mark health as degraded if data older than this
PORT = int(os.environ.get('PORT', 5001))  # Use PORT from environment (Fly.io) or default to 5001

# Structured Logging Setup
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
log_formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

# File handler with rotation
file_handler = RotatingFileHandler(
    'mta_tracker.log',
    maxBytes=512 * 1024,  # 512KB per file
    backupCount=3         # Total: ~2MB (512KB × 4 files)
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(getattr(logging, log_level))

# Configure app logger
app.logger.addHandler(console_handler)
app.logger.addHandler(file_handler)
app.logger.setLevel(getattr(logging, log_level))

# Global state
train_data = {
    'trains': [],
    'last_updated': None,
    'feed_version': None
}
stops_data = {}


# Security Headers Middleware
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    # Cache control for API endpoints
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'public, max-age=10'

    return response


def load_stops(stops_file):
    """Load station information from stops.txt"""
    stops = {}
    try:
        with open(stops_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stops[row['stop_id']] = {
                    'name': row['stop_name'],
                    'lat': float(row['stop_lat']),
                    'lon': float(row['stop_lon'])
                }
        app.logger.info(f"Loaded {len(stops)} stops from {stops_file}")
    except Exception as e:
        app.logger.error(f"Error loading stops from {stops_file}: {e}")
    return stops


def fetch_gtfs_feed(url):
    """Fetch the GTFS-RT protobuf feed from MTA"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception as e:
        app.logger.warning(f"Error fetching feed from {url}: {e}")
        return None


def parse_feed(feed_data):
    """Parse the protobuf feed and extract trip information"""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(feed_data)
    return feed


def extract_train_positions(feed, stops):
    """Extract active train information with positions"""
    trains = []
    current_time = datetime.now()

    for entity in feed.entity:
        if entity.HasField('trip_update'):
            trip_update = entity.trip_update
            trip = trip_update.trip

            # Extract basic trip information
            train_info = {
                'trip_id': trip.trip_id,
                'route_id': trip.route_id,
                'direction_id': trip.direction_id if trip.HasField('direction_id') else None,
                'stops': [],
                'current_stop_index': None,
                'position': None  # Will be calculated
            }

            # Extract stop time updates
            for idx, stop_update in enumerate(trip_update.stop_time_update):
                stop_id = stop_update.stop_id
                stop_data = stops.get(stop_id, {})

                stop_info = {
                    'stop_id': stop_id,
                    'stop_name': stop_data.get('name', stop_id),
                    'lat': stop_data.get('lat'),
                    'lon': stop_data.get('lon'),
                    'arrival_time': None,
                    'departure_time': None,
                    'arrival_timestamp': None
                }

                if stop_update.HasField('arrival'):
                    arrival_dt = datetime.fromtimestamp(stop_update.arrival.time)
                    stop_info['arrival_time'] = arrival_dt.strftime('%H:%M:%S')
                    stop_info['arrival_timestamp'] = stop_update.arrival.time

                if stop_update.HasField('departure'):
                    departure_dt = datetime.fromtimestamp(stop_update.departure.time)
                    stop_info['departure_time'] = departure_dt.strftime('%H:%M:%S')

                train_info['stops'].append(stop_info)

                # Determine current/next stop
                if train_info['current_stop_index'] is None:
                    if stop_info['arrival_timestamp']:
                        if arrival_dt > current_time:
                            train_info['current_stop_index'] = idx

            # Set default to first stop if none found
            if train_info['current_stop_index'] is None and len(train_info['stops']) > 0:
                train_info['current_stop_index'] = 0

            # Calculate position and direction
            if train_info['current_stop_index'] is not None:
                current_idx = train_info['current_stop_index']
                next_stop = train_info['stops'][current_idx]

                if next_stop['lat'] and next_stop['lon']:
                    train_info['position'] = {
                        'lat': next_stop['lat'],
                        'lon': next_stop['lon']
                    }

                    # Get previous stop for direction calculation
                    if current_idx > 0:
                        prev_stop = train_info['stops'][current_idx - 1]
                        if prev_stop['lat'] and prev_stop['lon']:
                            train_info['prev_position'] = {
                                'lat': prev_stop['lat'],
                                'lon': prev_stop['lon']
                            }

                    # Get next next stop for better direction if at current stop
                    if current_idx < len(train_info['stops']) - 1:
                        next_next_stop = train_info['stops'][current_idx + 1]
                        if next_next_stop['lat'] and next_next_stop['lon']:
                            train_info['next_position'] = {
                                'lat': next_next_stop['lat'],
                                'lon': next_next_stop['lon']
                            }

            trains.append(train_info)

    return trains


def update_train_data():
    """Background task to fetch and update train data from all feeds"""
    global train_data

    while True:
        try:
            app.logger.info("Fetching MTA feeds...")

            all_trains = []
            feed_counts = {}

            # Fetch from all feed URLs
            for feed_name, feed_url in FEED_URLS.items():
                try:
                    feed_data = fetch_gtfs_feed(feed_url)
                    if feed_data:
                        feed = parse_feed(feed_data)
                        trains = extract_train_positions(feed, stops_data)
                        all_trains.extend(trains)
                        feed_counts[feed_name] = len(trains)
                        app.logger.debug(f"{feed_name}: {len(trains)} trains")
                    else:
                        app.logger.warning(f"{feed_name}: Failed to fetch")
                        feed_counts[feed_name] = 0
                except Exception as e:
                    app.logger.error(f"{feed_name}: Error - {e}")
                    feed_counts[feed_name] = 0

            # Update global state
            train_data['trains'] = all_trains
            train_data['last_updated'] = datetime.now(timezone.utc).isoformat()
            train_data['feed_counts'] = feed_counts

            app.logger.info(f"Total: {len(all_trains)} active trains across all lines")

        except Exception as e:
            app.logger.error(f"Error updating train data: {e}", exc_info=True)

        time.sleep(UPDATE_INTERVAL)


@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('static', 'index.html')


@app.route('/api/trains')
def get_trains():
    """API endpoint to get current train data"""
    app.logger.debug(f"Serving train data from memory (client: {request.remote_addr})")
    return jsonify(train_data)


@app.route('/api/stops')
def get_stops():
    """API endpoint to get all stop locations"""
    # Convert stops dict to list for easier frontend consumption
    stops_list = [
        {
            'stop_id': stop_id,
            'name': data['name'],
            'lat': data['lat'],
            'lon': data['lon']
        }
        for stop_id, data in stops_data.items()
        if data.get('lat') and data.get('lon')
    ]
    return jsonify({'stops': stops_list})


@app.route('/api/health')
def health():
    """Health check endpoint with staleness detection"""
    last_update = train_data.get('last_updated')
    active_trains = len(train_data.get('trains', []))

    status = 'ok'
    reason = None

    # Check if data is stale
    if last_update:
        try:
            last_update_dt = datetime.fromisoformat(last_update)
            age_seconds = (datetime.now(timezone.utc) - last_update_dt).total_seconds()

            if age_seconds > DATA_STALE_THRESHOLD:
                status = 'degraded'
                reason = f'stale_data (age: {int(age_seconds)}s)'
                app.logger.warning(f"Health check: Data is stale ({int(age_seconds)}s old)")
        except Exception as e:
            app.logger.error(f"Health check: Error parsing last_updated: {e}")
            status = 'degraded'
            reason = 'invalid_timestamp'
    else:
        status = 'degraded'
        reason = 'no_data'

    response_data = {
        'status': status,
        'last_updated': last_update,
        'active_trains': active_trains,
        'feed_counts': train_data.get('feed_counts', {}),
        'hello': "world"
    }

    if reason:
        response_data['reason'] = reason

    status_code = 200 if status == 'ok' else 503
    return jsonify(response_data), status_code


if __name__ == '__main__':
    print("="*60)
    print("MTA Subway Tracker - Starting Server")
    print("="*60)

    # Load stops data
    print("\nLoading station data...")
    stops_data = load_stops(STOPS_FILE)

    # Start background thread for updating train data
    print("Starting background feed updater...")
    updater_thread = threading.Thread(target=update_train_data, daemon=True)
    updater_thread.start()

    # Give it a moment to fetch initial data
    print("Fetching initial data...\n")
    time.sleep(2)

    print("="*60)
    print("Server ready!")
    print(f"Open http://localhost:{PORT} in your browser")
    print(f"API available at http://localhost:{PORT}/api/trains")
    print("="*60)

    # Start Flask server
    # Security: debug=False for production
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=PORT, use_reloader=False)
