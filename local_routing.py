"""
Local Singapore road routing using OpenStreetMap data via OSMnx.

Used for post-solve route geometry (the polylines drawn on the map).
The CVRP solver itself uses real road shortest paths via igraph; see
route_optimizer.build_distance_and_time_matrices_real.

Returns: (distance_km: float, time_seconds: float, geometry: List[[lat, lng]])
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


def _annotate_bus_travel_times(g: nx.MultiDiGraph) -> None:
    """Add a per-edge `bus_travel_time` (seconds) attribute at factor=1.0
    base speed. The runtime safety factor is applied at output time in
    get_route_local — this keeps the cache factor-invariant.
    Imported lazily to avoid importing route_optimizer at module load."""
    from route_optimizer import edge_base_bus_speed_kmh
    for u, v, k, data in g.edges(keys=True, data=True):
        ln = data.get('length', 100)
        if isinstance(ln, list):
            ln = ln[0]
        try:
            ln = float(ln) if ln is not None else 100.0
        except (TypeError, ValueError):
            ln = 100.0
        speed = edge_base_bus_speed_kmh(data.get('highway'))
        data['bus_travel_time'] = ln * 3.6 / speed


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
        _annotate_bus_travel_times(_GRAPH)
    return _GRAPH


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _normalize_str(val) -> Optional[str]:
    """OSM attrs can come back as a list when an edge spans multiple ways."""
    if val is None:
        return None
    if isinstance(val, list):
        val = val[0] if val else None
    return str(val) if val is not None else None


def _normalize_float(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, list):
        val = val[0] if val else None
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def get_route_local(start_lat: float, start_lng: float,
                    end_lat: float, end_lng: float
                    ) -> Tuple[float, float, List[List[float]], List[dict]]:
    """
    Compute a drive route between two points using the local OSM graph.
    Returns (distance_km, time_seconds, geometry, road_parts).

    `road_parts` is a list of dicts, each describing a contiguous run of
    OSM edges that share the same (road_class, name, maxspeed). Used by
    the UI to render speed-heatmap polylines with per-segment tooltips:
        {coords, road_class, road_name, bus_speed_kmh,
         maxspeed_kmh, length_m, time_s}

    The current process-wide safety factor (route_optimizer.get_safety_factor)
    is applied to all reported speeds and times so the UI matches the solver.
    """
    from route_optimizer import edge_bus_speed_kmh, get_safety_factor

    factor = max(get_safety_factor(), 1e-6)
    inv_factor = 1.0 / factor

    g = get_graph()
    orig = ox.distance.nearest_nodes(g, X=start_lng, Y=start_lat)
    dest = ox.distance.nearest_nodes(g, X=end_lng,   Y=end_lat)

    if orig == dest:
        return 0.0, 0.0, [[start_lat, start_lng], [end_lat, end_lng]], []

    path = nx.shortest_path(g, orig, dest, weight='bus_travel_time')

    total_m = 0.0
    total_s = 0.0
    coords: List[List[float]] = []
    road_parts: List[dict] = []
    current_part: Optional[dict] = None

    def part_key(road_class, name, maxspeed):
        return (road_class, name, maxspeed)

    for u, v in zip(path[:-1], path[1:]):
        edge_data = g.get_edge_data(u, v)
        # MultiDiGraph: pick edge variant with the lowest school-bus time
        best = min(edge_data.values(),
                   key=lambda e: e.get('bus_travel_time', float('inf')))

        edge_len = _normalize_float(best.get('length')) or 0.0
        # bus_travel_time is cached at factor=1.0; scale to current factor.
        edge_time = (_normalize_float(best.get('bus_travel_time')) or 0.0) * inv_factor
        road_class = _normalize_str(best.get('highway')) or 'unclassified'
        road_name = _normalize_str(best.get('name'))
        maxspeed = _normalize_float(best.get('speed_kph'))
        bus_speed = round(edge_bus_speed_kmh(road_class), 1)

        total_m += edge_len
        total_s += edge_time

        geom = best.get('geometry')
        if geom is not None:
            # geom is a shapely LineString; coords are (lng, lat)
            pts = [[lat, lng] for lng, lat in geom.coords]
        else:
            u_node = g.nodes[u]
            v_node = g.nodes[v]
            pts = [[u_node['y'], u_node['x']], [v_node['y'], v_node['x']]]

        # Stitch into the flat geometry for backward compat
        if coords and pts and coords[-1] == pts[0]:
            coords.extend(pts[1:])
        else:
            coords.extend(pts)

        # Group consecutive edges that share (road_class, name, maxspeed)
        # so the UI doesn't have to render thousands of micro-polylines.
        key = part_key(road_class, road_name, maxspeed)
        if current_part is not None and current_part['_key'] == key:
            seam = current_part['coords']
            if seam and pts and seam[-1] == pts[0]:
                seam.extend(pts[1:])
            else:
                seam.extend(pts)
            current_part['length_m'] += edge_len
            current_part['time_s'] += edge_time
        else:
            current_part = {
                '_key': key,
                'coords': list(pts),
                'road_class': road_class,
                'road_name': road_name,
                'bus_speed_kmh': bus_speed,
                'maxspeed_kmh': round(maxspeed, 1) if maxspeed is not None else None,
                'length_m': edge_len,
                'time_s': edge_time,
            }
            road_parts.append(current_part)

    if coords:
        if coords[0] != [start_lat, start_lng]:
            coords.insert(0, [start_lat, start_lng])
        if coords[-1] != [end_lat, end_lng]:
            coords.append([end_lat, end_lng])

    # Drop the internal grouping key before returning
    for p in road_parts:
        p.pop('_key', None)
        p['length_m'] = round(p['length_m'], 1)
        p['time_s'] = round(p['time_s'], 1)

    return total_m / 1000.0, total_s, coords, road_parts


def warmup():
    """Prefetch the graph AND build the spatial index so the first user fetch is fast.

    Loading the graphml is only half the cost — the very first `nearest_nodes`
    call builds an internal KDTree over ~700k nodes (5-30s). Force that here.
    """
    g = get_graph()
    try:
        # Singapore centroid; result discarded — we just want the index built.
        ox.distance.nearest_nodes(g, X=103.85, Y=1.29)
        print("[local_routing] Spatial index ready.")
    except Exception as e:
        print(f"[local_routing] Spatial index warmup failed: {e}")
