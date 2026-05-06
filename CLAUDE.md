# CLAUDE.md — School Bus Route Planner

## Architecture overview

A Flask web app for planning optimal school bus routes in Singapore. Three-layer pipeline:

1. **Geography** — student addresses geocoded via OneMap API; school waypoint set manually or via search.
2. **Solver** — Google OR-Tools CVRP solver (`route_optimizer.py`) finds optimal bus routes using real-road distance/time matrices built from a local Singapore OSM graph. Rides are capped at a user-configurable max duration (enforced as a constraint via the CVRP time dimension).
3. **Post-solve geometry** — `local_routing.py` resolves per-segment drive paths (polylines + road_parts metadata) from the same OSM graph so the map shows realistic road-following routes.

Key files:

| File | Role |
|------|------|
| `app.py` | Flask app, API endpoints, vehicle-to-route assignment, CSV import |
| `route_optimizer.py` | CVRP solver, distance/time matrix builder (igraph over OSM), route-cache JSON |
| `local_routing.py` | OSMnx graph singleton, per-segment road geometry + speed-heatmap data |
| `onemap_utils.py` | OneMap API token management (auto-refresh, disk cache) |
| `models.py` | SQLAlchemy models: `RouteHistory`, `VehicleType`, `Vehicle` |
| `templates/index.html` | Single-page UI: Leaflet map, student list, accordion results, drag-and-drop reassignment |
| `chat_handler.py` | AI chat integration for route assistance |
| `sg_osm/` | Cached `singapore_drive.graphml` (~700k nodes, ~1.5M edges) |

Database: SQLite at `school_bus.db`. Tables auto-created on first request via `db.create_all()`.

## Run & build commands

```bash
# Install dependencies
pip install -r requirements.txt

# Set OneMap credentials in .env (ONEMAP_EMAIL + ONEMAP_PASSWORD, or ONEMAP_API_KEY)
cp .env.example .env

# Run (dev)
python app.py
# → http://localhost:5000

# Production (Render or similar)
# The app reads PORT env var and listens on 0.0.0.0 automatically.
```

No build step. No JS bundler. Leaflet + Lucide icons loaded from CDN.

## Code conventions & non-obvious design choices

### Safety factor trick
The CVRP solver applies a uniform "safety factor" (default 0.85) to all edge speeds — a scalar multiply on travel time. Because the factor is uniform, the OSM edge weights in the graph are cached at factor=1.0, and the factor is applied at output time. Changing the factor does NOT require rebuilding the road graph.

### Speed-limit hierarchy
Per-edge maxspeed from OSM is the primary base speed (94% of edges have it). The `SCHOOL_BUS_SPEED_KMH` dict in `route_optimizer.py` is a **class-median fallback** for the ~6% of edges without a maxspeed tag. The safety factor then scales everything down to reflect school-bus reality (dwell time, signals, school zones).

### Haversine-with-safety-factor fallback
When real-road distance lookups fail (cache miss + API failure), the solver falls back to Haversine distance × a detour factor. The safety factor is also applied to this estimated time.

### Frontend is a single 3500-line file
`templates/index.html` contains all HTML, CSS (inline `<style>`), and JS (inline `<script>`). No component framework. The UI uses:
- Leaflet 1.9.4 for the map (OneMap Singapore tiles)
- SortableJS for drag-and-drop student reassignment
- Lucide for icons
- Tailwind CSS via CDN

### Route accordion IDs
Each bus lane in results has `id="route-accordion-{i}"` and `data-route-index="{i}"`. The unassigned lane uses `id="unassignedLaneContainer"`. Map route layers map 1:1 to these accordions via the same index.

### Vehicle assignment (app.py)
Vehicles are fetched from DB (`status='active'`), sorted by capacity ascending. Routes are sorted by student count descending (largest first). Each route gets the smallest vehicle that can hold its students. Unmatched vehicles appear as "Unassigned vehicle" lanes.

### OSM graph warmup
`local_routing.warmup()` runs in a background thread on app startup. Loading the GraphML is half the cost; the first `nearest_nodes` call builds an internal KDTree over ~700k nodes (5-30s). The app forces this at startup so the first real request is fast.

### Route cache
`route_cache.json` stores solved routes keyed by a hash of input students + school location + parameters. Capped at 5000 entries. This is separate from the distance-matrix cache within the solver.

### Python version
Targets Python 3.11 (the `__pycache__` shows cpython-311). Windows development environment; deployment on Linux (Render).
