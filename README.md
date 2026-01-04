# NYC Subway Tracker

Real-time subway train tracker for NYC MTA using GTFS-RT feeds and Leaflet maps. Built by Aarif

## Features

- 🚇 **Real-time train tracking** for all major NYC subway lines (1-7, A-G, J-Z, L, N-W, S)
- 🗺️ **Interactive minimalist map** with train positions and station markers
- 🎨 **MTA official colors** for different subway lines
- ⚡ **Live updates** every 15 seconds
- 📍 **Directional arrows** showing actual travel direction (calculated from stop positions)
- 🎛️ **Route filtering** - beautiful animated checkbox controls to show/hide specific subway lines
- 🗺️ **NYC-focused map bounds** - zoom limited to metro area
- 📱 **Responsive design** for desktop and mobile

## Quick Start

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Download Station Data

The `stops.txt` file should already be present. If not, download it:

```bash
curl -L -o google_transit.zip http://web.mta.info/developers/data/nyct/subway/google_transit.zip
unzip -o google_transit.zip stops.txt
rm google_transit.zip
```

### 3. Run the Server

```bash
python3 app.py
```

### 4. Open in Browser

Navigate to: **http://localhost:5001**

## Project Structure

```
mta-tracker/
├── app.py              # Flask API backend
├── static/
│   └── index.html      # Frontend with Leaflet map
├── stops.txt           # Station coordinates (GTFS static data)
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

## API Endpoints

- `GET /` - Main web interface
- `GET /api/trains` - Current train positions and data
- `GET /api/stops` - All station locations
- `GET /api/health` - Server health check

## Tracked Lines

Currently tracking **23 routes** across **7 feeds**:
- **1/2/3 Lines** (Red - #EE352E)
- **4/5/6 Lines** (Green - #00933C)
- **7 Line** (Purple - #B933AD)
- **A/C/E Lines** (Blue - #0039A6)
- **B/D/F/M Lines** (Orange - #FF6319)
- **G Line** (Light Green - #6CBE45)
- **J/Z Lines** (Brown - #996633)
- **L Line** (Gray - #A7A9AC)
- **N/Q/R/W Lines** (Yellow - #FCCC0A)
- **S (Shuttle)** (Dark Gray - #808183)

**Default view:** Only shows 1, A, D, F, and L trains (customize via filter checkboxes)

## Adding More Lines

To add additional subway lines, edit `app.py`:

```python
FEED_URLS = {
    'JZ': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
    'ACE': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
    'BDFM': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
    'G': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
    'NQRW': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    # Add more feeds here
}
```

Available feeds: https://api.mta.info/#/subwayRealTimeFeeds

## Technologies Used

- **Backend**: Flask, Python 3
- **Frontend**: Leaflet.js, Vanilla JavaScript
- **Data**: MTA GTFS-RT (Protocol Buffers)
- **Map Tiles**: CartoDB Positron (minimalist style)

## How It Works

1. **Background Polling**: Flask server polls MTA GTFS-RT feeds every 15 seconds
2. **Data Processing**: Parses protobuf data and extracts train positions & directions
3. **API Serving**: Exposes train data via REST endpoints
4. **Frontend Updates**: Browser polls API every 15 seconds and updates map
5. **Position & Direction**: Trains are positioned at their next scheduled stop with directional arrows
6. **Minimalist Design**: Uses CartoDB Positron tiles for a clean, distraction-free map

## Deployment

Deploy to Fly.io (free tier, no sleep):

```bash
# Install Fly CLI
brew install flyctl

# Login
flyctl auth login

# Deploy from project directory
flyctl launch

# Follow prompts (choose app name, region)
# Then deployment starts automatically

# For future updates
git push
flyctl deploy
```

Your app will be live at: `https://your-app-name.fly.dev`

## License

MIT

## Credits

- MTA for real-time data feeds
- OpenStreetMap for map tiles
- Leaflet.js for mapping library
- Claude for making my life much easier
