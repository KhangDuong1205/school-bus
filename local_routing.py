"""
Local Singapore road routing using OpenStreetMap data via OSMnx.

Replaces the slow OneMap routing API for the "fetch real route geometry"
feature on the map. Distance/time estimates from this module are used purely
for visualisation — the CVRP optimiser still runs on Haversine distances.

Returns the same tuple shape as `route_optimizer.get_route_from_onemap`:
    (distance_km: float, time_seconds: float, geometry: List[[lat, lng]])
so it is a drop-in replacement.
"""
import os
import time
from threading import Lock
from typing import List, Tuple, Optional

import networkx as nx
import osmnx as ox

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_GRAPH: Optional[nx.MultiDiGraph] = None
_GRAPH_LOCK = Lock()

# Cache the prepared graph next to the PBF file so it persists between runs.
GRAPH_DIR = os.path.join(os.path.dirname(__file__), 'sg_osm')
GRAPH_CACHE = os.path.join(GRAPH_DIR, 'singapore_drive.graphml')
PLACE_QUERY = 'Singapore'

# Conservative urban-driving speeds in km/h, applied when OSM data is missing.
SPEED_DEFAULTS = {
    'motorway': 80, 'trunk': 70, 'primary': 60, 'secondary': 50,
    'tertiary': 45, 'unclassified': 40, 'residential': 30, 'service': 20,
    'living_street': 15,
}
SPEED_FALLBACK_KPH = 35


def _ensure_dir():
    if not os.path.isdir(GRAPH_DIR):
        os.makedirs(GRAPH_DIR, exist_ok=True)


def _build_graph_from_overpass() -> nx.MultiDiGraph:
    """First-run: download Singapore drive network via Overpass API."""
    print(f"[local_routing] Downloading {PLACE_QUERY} drive network from Overpass...")
    t0 = time.time()
    g = ox.graph_from_place(PLACE_QUERY, network_type='drive', simplify=True)
    g = ox.add_edge_speeds(g, hwy_speeds=SPEED_DEFAULTS, fallback=SPEED_FALLBACK_KPH)
    g = ox.add_edge_travel_times(g)
    print(f"[local_routing] Downloaded {len(g.nodes):,} nodes / {len(g.edges):,} edges in {time.time()-t0:.1f}s")
    _ensure_dir()
    ox.save_graphml(g, GRAPH_CACHE)
    print(f"[local_routing] Saved graph cache → {GRAPH_CACHE}")
    return g


def _load_cached_graph() -> nx.MultiDiGraph:
    print(f"[local_routing] Loading cached graph from {GRAPH_CACHE}...")
    t0 = time.time()
    g = ox.load_graphml(GRAPH_CACHE)
    print(f"[local_routing] Loaded in {time.time()-t0:.1f}s ({len(g.nodes):,} nodes)")
    return g


def get_graph() -> nx.MultiDiGraph:
    """Lazy singleton. Build/load on first call, reuse afterwards."""
    global _GRAPH
    if _GRAPH is not None:
        return _GRAPH
    with _GRAPH_LOCK:
        if _GRAPH is not None:
            return _GRAPH
        if os.path.exists(GRAPH_CACHE):
            _GRAPH = _load_cached_graph()
        else:
            _GRAPH = _build_graph_from_overpass()
    return _GRAPH


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def get_route_local(start_lat: float, start_lng: float,
                    end_lat: float, end_lng: float) -> Tuple[float, float, List[List[float]]]:
    """
    Compute a drive route between two points using the local OSM graph.
    Returns (distance_km, time_seconds, [[lat, lng], ...]).

    Falls back to a straight-line geometry on any error so callers never crash.
    """
    try:
        g = get_graph()
        orig = ox.distance.nearest_nodes(g, X=start_lng, Y=start_lat)
        dest = ox.distance.nearest_nodes(g, X=end_lng,   Y=end_lat)

        if orig == dest:
            return 0.0, 0.0, [[start_lat, start_lng], [end_lat, end_lng]]

        path = nx.shortest_path(g, orig, dest, weight='travel_time')

        # Aggregate distance + time along the path
        total_m = 0.0
        total_s = 0.0
        coords: List[List[float]] = []

        for u, v in zip(path[:-1], path[1:]):
            edge_data = g.get_edge_data(u, v)
            # MultiDiGraph: pick edge variant with the lowest travel time
            best = min(edge_data.values(),
                       key=lambda e: e.get('travel_time', float('inf')))
            total_m += best.get('length', 0.0)
            total_s += best.get('travel_time', 0.0)

            geom = best.get('geometry')
            if geom is not None:
                # geom is a shapely LineString; coords are (lng, lat)
                pts = [[lat, lng] for lng, lat in geom.coords]
                # Avoid duplicating join points
                if coords and pts and coords[-1] == pts[0]:
                    coords.extend(pts[1:])
                else:
                    coords.extend(pts)
            else:
                u_node = g.nodes[u]
                v_node = g.nodes[v]
                u_pt = [u_node['y'], u_node['x']]
                v_pt = [v_node['y'], v_node['x']]
                if not coords or coords[-1] != u_pt:
                    coords.append(u_pt)
                coords.append(v_pt)

        # Stitch the request endpoints onto the start/end of the road geometry
        if coords:
            if coords[0] != [start_lat, start_lng]:
                coords.insert(0, [start_lat, start_lng])
            if coords[-1] != [end_lat, end_lng]:
                coords.append([end_lat, end_lng])

        return total_m / 1000.0, total_s, coords

    except Exception as e:
        print(f"[local_routing] Routing failed ({e}); returning straight line.")
        return _straight_line_fallback(start_lat, start_lng, end_lat, end_lng)


def _straight_line_fallback(start_lat, start_lng, end_lat, end_lng):
    # Same haversine-based estimate the existing code uses, so callers see
    # consistent numbers if routing fails.
    import math
    R = 6371.0
    lat1, lat2 = math.radians(start_lat), math.radians(end_lat)
    dlat = math.radians(end_lat - start_lat)
    dlng = math.radians(end_lng - start_lng)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    distance_km = 2 * R * math.asin(math.sqrt(a)) * 1.5  # urban detour factor
    time_s = (distance_km / 35.0) * 3600.0
    return distance_km, time_s, [[start_lat, start_lng], [end_lat, end_lng]]


def warmup():
    """Optional: prefetch the graph on app startup so the first route is fast."""
    get_graph()
