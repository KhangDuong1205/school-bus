# School Bus Route Planner

A Python-based web application for planning optimal school bus routes using Singapore's OneMap API.

## Features
- Search and add student addresses using OneMap API
- Interactive map visualization with Leaflet.js
- Smart cluster analysis using DBSCAN algorithm
- Route optimization using Google OR-Tools CVRP solver
- Automatic bus capacity calculation (40 students per bus)
- Real-time statistics and route visualization
- Distance caching for improved performance
- Retry logic with exponential backoff for API reliability

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your OneMap API key
# Get your API key from: https://www.onemap.gov.sg/apidocs/
```

3. Run the application:
```bash
# Set environment variable (Windows)
set ONEMAP_API_KEY=your_api_key_here
python app.py

# Or (Linux/Mac)
export ONEMAP_API_KEY=your_api_key_here
python app.py
```

4. Open your browser to: http://localhost:5000

## Deployment (Render)

1. Set environment variable in Render dashboard:
   - Key: `ONEMAP_API_KEY`
   - Value: Your OneMap API key

2. The app will automatically use `0.0.0.0` and the PORT provided by Render

## API Endpoints

- `GET /api/cache/stats` - View cache statistics
- `POST /api/cache/clear` - Clear the distance cache

## Performance Features

- **Distance Caching**: API responses are cached to avoid repeated calls
- **Retry Logic**: Automatic retry with exponential backoff (1s, 2s, 4s)
- **Fallback**: Uses Haversine distance if API fails after retries
- **Security**: API key stored in environment variables
