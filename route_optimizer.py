"""
Route optimization algorithm for school bus routing
Uses Google OR-Tools CVRP solver with real driving distances
"""
import math
import json
import os
from typing import List, Dict, Tuple
import requests
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import numpy as np
import time
from threading import Lock
from onemap_utils import get_onemap_token

# Cache file path (in same directory as this script)
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'route_cache.json')
GRAPHML_PATH = os.path.join(os.path.dirname(__file__), 'sg_osm', 'singapore_drive.graphml')
MAX_CACHE_ENTRIES = 5000  # Limit cache size to prevent file from growing too large

# Per-edge `maxspeed` from OSM is the primary source of base cruise speed
# (94% of edges in singapore_drive.graphml have a maxspeed tag — the actual
# signposted statutory limit). The table below is a CLASS-MEDIAN FALLBACK
# for the ~6% of edges with no tag. Values are the median maxspeed observed
# per OSM highway class in the graph itself. Slow-down for school-bus
# reality (dwell, signals, school zones) is applied separately via the
# runtime safety factor (set_safety_factor).
SCHOOL_BUS_SPEED_KMH = {
    'motorway': 90,         'motorway_link': 50,
    'trunk': 60,            'trunk_link': 50,
    'primary': 60,          'primary_link': 50,
    'secondary': 50,        'secondary_link': 50,
    'tertiary': 50,         'tertiary_link': 50,
    'unclassified': 50,     'residential': 50,
    'living_street': 50,    'service': 18,
}
SCHOOL_BUS_SPEED_DEFAULT_KMH = 50       # SG urban default when both maxspeed and highway tag missing

# Global safety factor applied uniformly to every road class.
# 1.0 = no margin (raw cruise speed); lower = more conservative.
# User-tunable per request via set_safety_factor() / the UI.
#
# Implementation note: because the factor is uniform, time = base/factor
# is just a scalar multiply on the base time matrix — we DO NOT rebuild
# the cached road graph when the factor changes. The cache stores edge
# weights at factor=1.0 (computed via edge_base_bus_speed_kmh), and the
# factor is applied at output (matrix scaling + per-edge display speed).
SAFETY_FACTOR_DEFAULT = 0.85
SAFETY_FACTOR_MIN = 0.1   # 10% of maxspeed — extreme but legal; below 0.1 is absurd
SAFETY_FACTOR_MAX = 1.0
_current_safety_factor = SAFETY_FACTOR_DEFAULT


def set_safety_factor(f) -> float:
    """Update the process-wide bus speed safety factor and return the
    clamped value actually applied. Note: this is a global — concurrent
    requests with different factors will race. The codebase already uses
    this pattern (see _road_graph_state) and Flask requests are typically
    serial in practice."""
    global _current_safety_factor
    try:
        f_in = float(f)
    except (TypeError, ValueError):
        print(f"[safety_factor] WARN: invalid input {f!r}, using default {SAFETY_FACTOR_DEFAULT}", flush=True)
        _current_safety_factor = SAFETY_FACTOR_DEFAULT
        return SAFETY_FACTOR_DEFAULT
    f = max(SAFETY_FACTOR_MIN, min(SAFETY_FACTOR_MAX, f_in))
    if f != f_in:
        print(f"[safety_factor] WARN: input {f_in} clamped to {f} "
              f"(allowed range {SAFETY_FACTOR_MIN}-{SAFETY_FACTOR_MAX})", flush=True)
    _current_safety_factor = f
    return f


def get_safety_factor() -> float:
    return _current_safety_factor


def edge_base_bus_speed_kmh(highway_tag) -> float:
    """Class-level fallback cruise speed (km/h) for an OSM road class —
    no safety factor. Used when an edge has no `maxspeed` tag, or by the
    road-types overlay which represents the class table itself."""
    if isinstance(highway_tag, list):
        highway_tag = highway_tag[0] if highway_tag else None
    if highway_tag is None:
        return SCHOOL_BUS_SPEED_DEFAULT_KMH
    return SCHOOL_BUS_SPEED_KMH.get(str(highway_tag), SCHOOL_BUS_SPEED_DEFAULT_KMH)


def edge_bus_speed_kmh(highway_tag) -> float:
    """Class-level effective cruise speed (km/h) including safety factor.
    Used by the road-types overlay (class table view); per-edge solver/UI
    display goes through edge_bus_speed_for_edge instead."""
    return edge_base_bus_speed_kmh(highway_tag) * _current_safety_factor


def _parse_edge_maxspeed_kmh(edge_data) -> float:
    """Extract a per-edge maxspeed in km/h from an OSM edge data dict.
    Handles list-valued attrs (edge spans multiple ways), 'NN km/h',
    'NN mph', and non-numeric tags ('signals', 'walk'). Returns None when
    no usable maxspeed is present."""
    v = edge_data.get('maxspeed')
    if isinstance(v, list):
        v = v[0] if v else None
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        pass
    s = str(v).strip().lower()
    if not s or s in ('none', 'signals', 'walk', 'variable'):
        return None
    is_mph = 'mph' in s
    digits = ''
    for ch in s:
        if ch.isdigit() or ch == '.':
            digits += ch
        elif digits:
            break
    if not digits:
        return None
    try:
        n = float(digits)
    except ValueError:
        return None
    return n * 1.60934 if is_mph else n


def edge_base_bus_speed_for_edge(edge_data) -> float:
    """Per-edge base cruise speed (km/h) at factor=1.0. Prefers the OSM
    `maxspeed` for that specific edge; falls back to the class-median in
    SCHOOL_BUS_SPEED_KMH when the edge has no maxspeed tag."""
    ms = _parse_edge_maxspeed_kmh(edge_data)
    if ms is not None and ms > 0:
        return ms
    return edge_base_bus_speed_kmh(edge_data.get('highway'))


def edge_bus_speed_for_edge(edge_data) -> float:
    """Per-edge effective cruise speed (km/h) including safety factor."""
    return edge_base_bus_speed_for_edge(edge_data) * _current_safety_factor


_road_graph_state = {'ig': None, 'tree': None, 'node_ids': None}
_road_graph_lock = Lock()


def _get_road_graph():
    """Lazily load Singapore road graph into igraph + a haversine BallTree
    for nearest-node lookup. Cached for the process lifetime."""
    if _road_graph_state['ig'] is not None:
        return _road_graph_state
    with _road_graph_lock:
        if _road_graph_state['ig'] is not None:
            return _road_graph_state

        import osmnx as ox
        import igraph as ig
        from sklearn.neighbors import BallTree

        print(f"[graph] Loading {GRAPHML_PATH}", flush=True)
        nx_g = ox.load_graphml(GRAPHML_PATH)
        print(f"[graph] {len(nx_g.nodes)} nodes, {len(nx_g.edges)} edges", flush=True)

        node_list = list(nx_g.nodes)
        node_to_idx = {n: i for i, n in enumerate(node_list)}

        edges, lengths, bus_travel_times = [], [], []
        for u, v, d in nx_g.edges(data=True):
            edges.append((node_to_idx[u], node_to_idx[v]))
            ln = d.get('length', 100)
            if isinstance(ln, list):
                ln = ln[0]
            try:
                ln = float(ln) if ln is not None else 100.0
            except (TypeError, ValueError):
                ln = 100.0
            lengths.append(ln)
            # Per-edge time at base cruise speed (factor=1.0). The runtime
            # safety factor is applied as a scalar multiply on the final
            # time matrix — this keeps the cache factor-invariant. Speed
            # comes from the edge's own `maxspeed` tag, with class-median
            # fallback when missing.
            speed_kmh = edge_base_bus_speed_for_edge(d)
            bus_travel_times.append(ln * 3.6 / speed_kmh)

        g = ig.Graph(n=len(node_list), edges=edges, directed=True)
        g.es['length'] = lengths
        g.es['bus_travel_time'] = bus_travel_times

        coords = np.array([
            [float(nx_g.nodes[n]['y']), float(nx_g.nodes[n]['x'])]
            for n in node_list
        ])
        tree = BallTree(np.radians(coords), metric='haversine')

        _road_graph_state['ig'] = g
        _road_graph_state['tree'] = tree
        _road_graph_state['node_ids'] = node_list
        print("[graph] Indexed and ready.", flush=True)
        return _road_graph_state


def _nearest_graph_nodes(points: List[Dict]) -> List[int]:
    """Map a list of {latitude, longitude} dicts to igraph vertex indices."""
    state = _get_road_graph()
    coords = np.radians(np.array([
        [float(p['latitude']), float(p['longitude'])] for p in points
    ]))
    _, indices = state['tree'].query(coords, k=1)
    return indices[:, 0].tolist()


def build_distance_and_time_matrices_real(
    school: Dict, students: List[Dict]
) -> Tuple[List[List[int]], List[List[int]]]:
    """Build (distance_m, time_s) matrices via Dijkstra on the real Singapore
    road graph.

    - `bus_travel_time` weight: per-edge time at base cruise speed —
      OSM `maxspeed` for that edge when tagged (94% of edges), with
      SCHOOL_BUS_SPEED_KMH class-median as fallback. Used to find the
      time-optimal path AND to report total time.
    - `length` weight: shortest physical distance (meters) reported separately.
    """
    state = _get_road_graph()
    g = state['ig']

    points = [school] + students
    n = len(points)
    src_nodes = _nearest_graph_nodes(points)

    print(f"[matrix] Real-road shortest paths for {n} points...", flush=True)

    distance_matrix = [[0] * n for _ in range(n)]
    time_matrix = [[0] * n for _ in range(n)]

    INF = float('inf')
    UNREACHABLE_M = 99_999_000
    UNREACHABLE_S = 9_999_000

    # Cached edge weights are at factor=1.0; divide by current factor to
    # apply the user's safety margin uniformly to every pair.
    factor = max(_current_safety_factor, 1e-6)
    inv_factor = 1.0 / factor

    # Two single-source Dijkstras per point: one by bus_travel_time (gives
    # time-optimal path cost), one by length (gives distance-optimal path
    # cost). They may pick different paths for some pairs, but the solver
    # uses each matrix for its respective constraint (time / distance).
    for i in range(n):
        time_all = g.distances(source=src_nodes[i], weights='bus_travel_time', mode='all')[0]
        len_all = g.distances(source=src_nodes[i], weights='length', mode='all')[0]
        for j in range(n):
            t = time_all[src_nodes[j]]
            d = len_all[src_nodes[j]]
            if t == INF or d == INF:
                distance_matrix[i][j] = UNREACHABLE_M
                time_matrix[i][j] = UNREACHABLE_S
            else:
                distance_matrix[i][j] = int(d)
                time_matrix[i][j] = int(t * inv_factor)

    print(f"[matrix] Built (safety factor: {factor:.2f}).", flush=True)
    return distance_matrix, time_matrix

# Global cache for distance/route data to avoid repeated API calls
distance_cache = {}
route_geometry_cache = {}
postal_code_cache = {}  # Cache for reverse geocoding
cache_school_hash = None  # Track school location for cache invalidation

# Rate limiting for API calls - Lock initialized at module level to avoid race condition
rate_limit_lock = Lock()
cache_lock = Lock()  # For thread-safe cache file access
last_api_call_time = 0
MIN_API_INTERVAL = 0.2  # 200ms between calls = max 5/sec
_api_healthy = True  # Set to False after first auth failure to skip retries


def load_cache_from_file():
    """Load cache from JSON file on startup"""
    global distance_cache, route_geometry_cache
    
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                distance_cache = data.get('distance_cache', {})
                distance_cache = data.get('distance_cache', {})
                route_geometry_cache = data.get('route_geometry_cache', {})
                postal_code_cache = data.get('postal_code_cache', {})
                print(f"Loaded cache: {len(distance_cache)} distance, {len(route_geometry_cache)} geometry, {len(postal_code_cache)} postal entries")
    except Exception as e:
        print(f"Could not load cache file: {e}")
        distance_cache = {}
        route_geometry_cache = {}


def save_cache_to_file():
    """Save cache to JSON file"""
    with cache_lock:
        try:
            # Prune cache if too large
            if len(distance_cache) > MAX_CACHE_ENTRIES:
                keys_to_remove = list(distance_cache.keys())[:-MAX_CACHE_ENTRIES]
                for key in keys_to_remove:
                    del distance_cache[key]
            
            data = {
                'distance_cache': distance_cache,
                'route_geometry_cache': route_geometry_cache,
                'postal_code_cache': postal_code_cache
            }
            with open(CACHE_FILE, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Could not save cache file: {e}")


# Load cache on module import
load_cache_from_file()


def get_cache_stats() -> Dict:
    """Get statistics about the cache"""
    return {
        'distance_cache_size': len(distance_cache),
        'route_geometry_cache_size': len(route_geometry_cache),
        'postal_code_cache_size': len(postal_code_cache),
        'total_cached_items': len(distance_cache) + len(route_geometry_cache) + len(postal_code_cache),
        'cache_file': CACHE_FILE,
        'cache_file_exists': os.path.exists(CACHE_FILE)
    }


def clear_cache():
    """Clear all caches"""
    global distance_cache, route_geometry_cache, cache_school_hash, postal_code_cache
    distance_cache.clear()
    route_geometry_cache.clear()
    postal_code_cache.clear()
    cache_school_hash = None
    save_cache_to_file()  # Also clear the file
    print("Cache cleared")


def invalidate_cache_if_school_changed(school: Dict):
    """Invalidate cache if school location has changed"""
    global cache_school_hash, distance_cache, route_geometry_cache, postal_code_cache
    
    # Create hash of school location
    school_hash = f"{school['latitude']:.4f},{school['longitude']:.4f}"
    
    if cache_school_hash is None:
        cache_school_hash = school_hash
    elif cache_school_hash != school_hash:
        print("School location changed - clearing cache")
        distance_cache.clear()
        route_geometry_cache.clear()
        cache_school_hash = school_hash


def get_real_route_geometry_for_segments(route_segments: List[Dict], api_key: str = None) -> List[Dict]:
    """
    Get real road geometry for route segments using local OSM data (OSMnx).
    Called AFTER optimization to display real roads on the map.

    `api_key` is unused (kept for backwards compatibility).

    Time is computed via per-edge SCHOOL_BUS_SPEED_KMH (motorway 72,
    residential 22, etc.) — same source of truth as the solver matrix.
    """
    from concurrent.futures import ThreadPoolExecutor
    from local_routing import get_route_local, get_graph

    # Pre-load the graph once (no-op if already loaded) so worker threads share it
    get_graph()

    n = len(route_segments)
    print(f"Fetching road geometry for {n} segments via local OSM graph...", flush=True)

    def route_one(item):
        i, segment = item
        try:
            p_from = segment['from']
            p_to = segment['to']
            from_lat = p_from.get('lat') or p_from.get('latitude')
            from_lng = p_from.get('lng') or p_from.get('longitude')
            to_lat = p_to.get('lat') or p_to.get('latitude')
            to_lng = p_to.get('lng') or p_to.get('longitude')

            if not (from_lat and from_lng and to_lat and to_lng):
                return i, segment

            distance_km, time_s, geometry, road_parts = get_route_local(
                from_lat, from_lng, to_lat, to_lng
            )
            segment['geometry'] = geometry
            segment['road_parts'] = road_parts
            segment['distance'] = distance_km
            segment['time'] = time_s
            return i, segment
        except Exception as e:
            print(f"\n  Segment {i} failed: {e}", flush=True)
            return i, segment

    enriched = [None] * n
    # NetworkX read-only Dijkstra is thread-safe; 8 workers is plenty
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, seg in ex.map(route_one, list(enumerate(route_segments))):
            enriched[i] = seg

    print(f"Road geometry fetched ({n} segments).", flush=True)
    return enriched

def get_postal_code(lat: float, lng: float, api_key: str) -> str:
    """
    Get postal code from coordinates using OneMap Reverse Geocoding API.
    Uses caching and rate limiting.
    """
    global last_api_call_time, postal_code_cache
    
    # Create cache key (4 decimal places ~11m precision)
    cache_key = f"{lat:.4f},{lng:.4f}"
    
    # Check cache
    if cache_key in postal_code_cache:
        return postal_code_cache[cache_key]
    
    # Rate limiting
    with rate_limit_lock:
        elapsed = time.time() - last_api_call_time
        if elapsed < MIN_API_INTERVAL:
            time.sleep(MIN_API_INTERVAL - elapsed)
        last_api_call_time = time.time()
    
    try:
        url = "https://www.onemap.gov.sg/api/public/revgeocode"
        params = {
            'location': f"{lat},{lng}",
            'buffer': 40,
            'addressType': 'All'
        }
        headers = {'Authorization': api_key}
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
#         print(f"  Geocode API: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            # OneMap revgeocode returns 'GeocodeInfo' list
            if 'GeocodeInfo' in data and data['GeocodeInfo']:
                # Helper to find best postal match
                # Prefer building with postal code
                best_match = data['GeocodeInfo'][0]
                postal = best_match.get('POSTALCODE', '')
                
                # If 'NIL' or empty, look for others
                if postal == 'NIL' or not postal:
                    for info in data['GeocodeInfo']:
                        p = info.get('POSTALCODE', '')
                        if p and p != 'NIL':
                            postal = p
                            break
                
                # Cache result (save 'NIL' too to avoid refetching bad coords)
                postal_code_cache[cache_key] = postal
                save_cache_to_file() # Save periodically
                return postal
            else:
                postal_code_cache[cache_key] = ""
                return ""
        else:
            print(f"Reverse geocode failed: {response.status_code} - {response.text[:100]}")
            return ""
            
    except Exception as e:
        print(f"Reverse geocode exception: {e}")
        return ""


def two_opt(route_indices: List[int], distance_matrix: List[List[int]]) -> Tuple[List[int], float]:
    """
    Improve route using 2-opt local search algorithm.
    Repeatedly reverses segments of the route if it reduces total distance.
    
    Args:
        route_indices: List of node indices representing the route (starts and ends at depot 0)
        distance_matrix: Distance matrix in meters
    
    Returns:
        Tuple of (improved_route_indices, improvement_percentage)
    """
    def calculate_route_distance(route):
        return sum(distance_matrix[route[i]][route[i+1]] for i in range(len(route) - 1))
    
    route = route_indices.copy()
    original_distance = calculate_route_distance(route)
    
    if original_distance == 0:
        return route, 0.0
    
    improved = True
    iteration = 0
    max_iterations = 100  # Prevent infinite loops
    
    while improved and iteration < max_iterations:
        improved = False
        iteration += 1
        
        for i in range(1, len(route) - 2):
            for j in range(i + 1, len(route) - 1):
                # Calculate the change in distance if we reverse the segment from i to j
                # Current edges: (i-1, i) and (j, j+1)
                # New edges after reversal: (i-1, j) and (i, j+1)
                
                old_dist = (distance_matrix[route[i-1]][route[i]] + 
                           distance_matrix[route[j]][route[j+1]])
                new_dist = (distance_matrix[route[i-1]][route[j]] + 
                           distance_matrix[route[i]][route[j+1]])
                
                if new_dist < old_dist:
                    # Reverse the segment from i to j (inclusive)
                    route[i:j+1] = route[i:j+1][::-1]
                    improved = True
                    break
            
            if improved:
                break
    
    new_distance = calculate_route_distance(route)
    improvement = ((original_distance - new_distance) / original_distance) * 100
    
    return route, improvement


def apply_two_opt_to_route(route_students: List[Dict], distance_matrix: List[List[int]]) -> Tuple[List[Dict], float]:
    """
    Apply 2-opt optimization to reorder students in a route.
    
    Args:
        route_students: List of student dictionaries in current order
        distance_matrix: Full distance matrix
    
    Returns:
        Tuple of (reordered_students, improvement_percentage)
    """
    if len(route_students) <= 2:
        return route_students, 0.0
    
    # Build route indices (depot=0, then student indices)
    # Students are 1-indexed in the distance matrix (index 0 is school)
    route_indices = [0]  # Start at school
    for student in route_students:
        # Find the student's index in the distance matrix
        # This assumes students maintain their original index from the students list
        if 'matrix_index' in student:
            route_indices.append(student['matrix_index'])
        else:
            # Fallback: use position in list + 1
            route_indices.append(route_students.index(student) + 1)
    route_indices.append(0)  # Return to school
    
    # Apply 2-opt
    optimized_indices, improvement = two_opt(route_indices, distance_matrix)
    
    if improvement <= 0:
        return route_students, 0.0
    
    # Reorder students according to optimized indices
    # Skip first and last (depot)
    optimized_student_indices = optimized_indices[1:-1]
    
    # Map indices back to students
    index_to_student = {}
    for student in route_students:
        if 'matrix_index' in student:
            index_to_student[student['matrix_index']] = student
        else:
            index_to_student[route_students.index(student) + 1] = student
    
    reordered_students = []
    for idx in optimized_student_indices:
        if idx in index_to_student:
            reordered_students.append(index_to_student[idx])
    
    # If reordering failed, return original
    if len(reordered_students) != len(route_students):
        return route_students, 0.0
    
    return reordered_students, improvement

def format_time(seconds_from_midnight: int) -> str:
    """Convert seconds from midnight to HH:MM AM/PM format"""
    hours = (seconds_from_midnight // 3600) % 24
    minutes = (seconds_from_midnight % 3600) // 60
    period = "AM" if hours < 12 else "PM"
    display_hour = hours if hours <= 12 else hours - 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:{minutes:02d} {period}"


def _build_cvrp_model(school: Dict, students: List[Dict], num_vehicles: int,
                       distance_matrix, max_ride_time_minutes: int,
                       vehicle_capacities: List[int] = None,
                       time_matrix=None,
                       advanced_params: Dict = None,
                       demands: List[int] = None):
    if advanced_params is None:
        advanced_params = {
            'service_time': 60,
            'base_bus_cost': 5000,
            'penalty_per_seat': 200
        }
    """
    Build and return a CVRP model (manager, routing, callbacks) without solving.
    Shared by both Phase 1 and Phase 2 of two-phase solving.
    """
    manager = pywrapcp.RoutingIndexManager(
        len(distance_matrix), num_vehicles, 0
    )
    routing = pywrapcp.RoutingModel(manager)
    
    # Distance callback (open-ended: school->student cost = 0)
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        if from_node == 0 and to_node > 0:
            return 0
        return distance_matrix[from_node][to_node]
    
    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    
    # Capacity constraint
    if vehicle_capacities and len(vehicle_capacities) == num_vehicles:
        capacities = vehicle_capacities
    else:
        capacities = [40] * num_vehicles
    
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        if demands is not None:
            return demands[from_node]
        return 1 if from_node > 0 else 0
    
    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index, 0, capacities, True, 'Capacity'
    )

    capacity_dimension = routing.GetDimensionOrDie('Capacity')

    VEHICLE_FIXED_COST_BASE = advanced_params['base_bus_cost']
    for vehicle_id in range(num_vehicles):
        vehicle_capacity = capacities[vehicle_id]
        capacity_penalty = (vehicle_capacity - 20) * advanced_params['penalty_per_seat']
        fixed_cost = VEHICLE_FIXED_COST_BASE + capacity_penalty
        routing.SetFixedCostOfVehicle(fixed_cost, vehicle_id)

    # Time constraint — uses REAL travel times from API when available
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        
        node_demand = demands[to_node] if (demands is not None and to_node > 0) else (1 if to_node > 0 else 0)
        pickup_time = advanced_params['service_time'] + (node_demand - 1) * 15 if to_node > 0 and node_demand > 0 else 0
        
        if from_node == 0 and to_node > 0:
            return pickup_time  # Just pickup time for OVRP start
        travel_time = time_matrix[from_node][to_node]
        return int(travel_time + pickup_time)
    
    time_callback_index = routing.RegisterTransitCallback(time_callback)
    
    # Hard cap = user's max_ride_time exactly. The violation check at
    # solve_cvrp:920 / enrich_routes_with_geometry:1037 compares against
    # the same value, so any buffer here would silently allow rides the
    # check then flags as violations.
    global_hard_cap = int(max_ride_time_minutes * 60)

    routing.AddDimension(
        time_callback_index, slack_max=1800, capacity=global_hard_cap,
        fix_start_cumul_to_zero=True, name='Time'
    )

    time_dimension = routing.GetDimensionOrDie('Time')

    # Minimal span costs — let solver dispatch freely
    time_dimension.SetGlobalSpanCostCoefficient(0)
    for vehicle_id in range(num_vehicles):
        time_dimension.SetSpanCostCoefficientForVehicle(0, vehicle_id)

    # --- ADVANCED CONSTRAINTS ---
    solver = routing.solver()

    # 1. Sibling Constraint: Group students with the same family code
    family_groups = {}
    for i, student in enumerate(students):
        fc = student.get('family_code')
        if fc and str(fc).strip():
            family_groups.setdefault(str(fc).strip(), []).append(i + 1)  # +1 because 0 is school
            
    for fc, members in family_groups.items():
        if len(members) > 1:
            for i in range(len(members) - 1):
                current_node = members[i]
                next_node = members[i + 1]
                # Force siblings to be assigned to the same vehicle
                solver.Add(routing.VehicleVar(current_node) == routing.VehicleVar(next_node))
                # Force siblings to be picked up consecutively (breaks symmetry and guarantees group pickup)
                solver.Add(routing.NextVar(current_node) == next_node)
                
    # 2. Special Needs Constraint: hard cap of 30 min on time_dimension.
    # time_dimension already includes the safety factor (time_matrix is
    # scaled by 1/factor in build_distance_and_time_matrices_real), so
    # 1800s here is in conservative-speed seconds — same units the user's
    # max_ride_time soft bound is compared against. No extra factor needed.
    special_needs_max_time = 1800
    M = global_hard_cap * 2  # Big-M for implication
    
    for i, student in enumerate(students):
        if student.get('special_needs'):
            node = i + 1
            for v in range(num_vehicles):
                # is_on_v will be 1 if student is on bus v, else 0
                is_on_v = solver.IsEqualCstVar(routing.VehicleVar(node), v)
                
                # If on bus v, end_time - pickup_time <= special_needs_max_time
                # Using Big-M: end_time - pickup_time - special_needs_max_time <= M * (1 - is_on_v)
                eq = time_dimension.CumulVar(routing.End(v)) - time_dimension.CumulVar(node)
                solver.Add(eq - special_needs_max_time <= M * (1 - is_on_v))
                
    return manager, routing, capacities


def solve_cvrp(school: Dict, students: List[Dict], num_vehicles: int, api_key: str, 
               max_route_time_minutes: int = 60,
               school_arrival_time: int = 27000,
               max_ride_time_minutes: int = 60,
               vehicle_capacities: List[int] = None,
               advanced_params: Dict = None) -> Dict:
    """
    CVRP solver. Builds a real-road distance/time matrix via igraph Dijkstra
    on the cached Singapore OSM graph (NOT haversine — the older comment
    saying 'fast Haversine estimates' was a holdover from an early version).
    Phase 2 polyline enrichment happens in enrich_routes_with_geometry,
    which the app calls separately after this returns.
    """
    if not students:
        return {'routes': [], 'total_distance': 0, 'total_time': 0}
    
    # --- SUPER NODE LOGIC: Group students at identical coordinates ---
    location_groups = {}
    for s in students:
        # Group by 5 decimals (~1.1m precision)
        key = (round(s['latitude'], 5), round(s['longitude'], 5))
        if key not in location_groups:
            location_groups[key] = []
        location_groups[key].append(s)

    super_nodes = []
    demands = [0]  # Demand for school/depot is 0
    for loc, st_list in location_groups.items():
        rep = st_list[0].copy()
        rep['grouped_students'] = st_list
        rep['special_needs'] = any(s.get('special_needs') for s in st_list)
        super_nodes.append(rep)
        demands.append(len(st_list))

    print(f"Grouped {len(students)} students into {len(super_nodes)} distinct locations.")
    
    # Use super_nodes for routing logic
    original_students = students
    students = super_nodes
    # --- END SUPER NODE LOGIC ---

    distance_matrix, time_matrix = build_distance_and_time_matrices_real(school, students)

    # Let the solver use all available vehicles. Low fixed cost (500)
    # means it will naturally prefer adding a bus over violating 60 min,
    # but won't waste vehicles unnecessarily.
    n_students_actual = sum(demands)
    min_buses = max(1, math.ceil(n_students_actual / 40))
    print(f"Available: {num_vehicles} vehicles, {n_students_actual} students "
          f"(min ~{min_buses} buses at 40/bus)")

    # Time limit scales with unique locations: 45s-180s range
    solver_time_limit = max(45, min(180, int(len(students) * 0.8)))
    print(f"\n--- Solving with up to {num_vehicles} vehicles ({solver_time_limit}s) ---")

    manager, routing, capacities = _build_cvrp_model(
        school, students, num_vehicles, distance_matrix,
        max_ride_time_minutes, vehicle_capacities, time_matrix,
        advanced_params=advanced_params, demands=demands
    )

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.SAVINGS
    )
    search_params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.TABU_SEARCH
    )
    search_params.time_limit.seconds = solver_time_limit
    
    solution = routing.SolveWithParameters(search_params)
    
    if not solution:
        return {'error': 'No solution found (constraints too tight?)'}
    
    # vehicle_map simply maps 1:1 since we are running with all initial vehicles
    vehicle_map = list(range(num_vehicles))
    
    # ===== EXTRACT ROUTES (real road distances + times from solver matrices) =====
    routes = []
    total_distance = 0
    max_route_time = 0
    max_student_ride_time = 0
    time_violations = []
    
    time_dimension = routing.GetDimensionOrDie('Time')
    
    for vehicle_id in range(num_vehicles):
        # Determine original fleet index if available
        original_vehicle_index = vehicle_map[vehicle_id] if vehicle_map else vehicle_id
        
        index = routing.Start(vehicle_id)
        departure_time = solution.Min(time_dimension.CumulVar(index))
        
        route_distance = 0
        route_time = 0
        route_students = []
        route_segments = []
        cumulative_time = 0
        
        # Temporary storage for students on this route to process times after total duration is known
        temp_route_data = []
        
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            next_index = solution.Value(routing.NextVar(index))
            next_node = manager.IndexToNode(next_index)
            
            if node_index == 0 and next_node == 0:
                break
            
            if next_node != 0:
                super_node = students[next_node - 1]
                node_demand = len(super_node.get('grouped_students', [super_node]))
                
                if node_index == 0:
                    distance_km = 0
                    time_s = 0
                else:
                    distance_km = distance_matrix[node_index][next_node] / 1000
                    time_s = time_matrix[node_index][next_node]
                
                service_time = advanced_params['service_time'] if advanced_params else 60
                
                route_distance += distance_km
                total_pickup_time = service_time + (node_demand - 1) * 15 if node_demand > 0 else 0
                route_time += time_s + total_pickup_time
                cumulative_time += time_s
                
                # Store data for EACH individual student in the super node
                for i, act_student in enumerate(super_node.get('grouped_students', [super_node])):
                    temp_route_data.append({
                        'student': act_student,
                        'relative_pickup_time': cumulative_time,
                        'segment_from': students[node_index - 1] if node_index > 0 else None,
                        'segment_to': act_student
                    })
                    cumulative_time += service_time if i == 0 else 15
                
                # Add ONE segment to this location
                prev_student = students[node_index - 1] if node_index > 0 else None
                
                # OPEN VRP: Only add segment if there IS a previous student.
                if prev_student:
                    segment_name = super_node.get('name', super_node.get('Name', 'Student')) if node_demand == 1 else f"{node_demand} pax at {super_node.get('address', 'this location')}"
                    route_segments.append({
                        'from': {'lat': prev_student['latitude'], 'lng': prev_student['longitude']},
                        'to': {'lat': super_node['latitude'], 'lng': super_node['longitude']},
                        'student': segment_name
                    })

            else:
                from_point = students[node_index - 1] if node_index > 0 else school
                distance_km = distance_matrix[node_index][0] / 1000
                time_s = time_matrix[node_index][0]
                
                route_distance += distance_km
                route_time += time_s
                cumulative_time += time_s
                
                route_segments.append({
                    'from': {'lat': from_point['latitude'], 'lng': from_point['longitude']},
                    'to': {'lat': school['latitude'], 'lng': school['longitude']},
                    'student': 'Return to School'
                })
            
            index = next_index

        # Now calculate actual times based on total route duration
        # Determine actual start time based on school arrival time
        actual_departure_time = school_arrival_time - int(route_time)

        for item in temp_route_data:
            student = item['student']
            rel_pickup = item['relative_pickup_time']
            
            actual_pickup = actual_departure_time + rel_pickup
            ride_duration = school_arrival_time - actual_pickup
            
            max_student_ride_time = max(max_student_ride_time, ride_duration)
            
            if ride_duration > max_ride_time_minutes * 60:
                time_violations.append({
                    'student': student.get('name', student.get('Name', 'Unknown')),
                    'ride_minutes': round(ride_duration / 60, 1),
                    'bus': vehicle_id + 1
                })
            
            route_students.append({
                **student,
                'pickup_time': format_time(int(actual_pickup)),
                'ride_duration_minutes': round(ride_duration / 60, 1)
            })
        
        if route_students:
            print(f"  Bus {vehicle_id + 1}: {len(route_students)} students")
            
            # Solver-matrix times; geometry polylines fetched lazily per route
            actual_departure_time = school_arrival_time - int(route_time)
            
            routes.append({
                'students': route_students,
                'distance_km': round(route_distance, 2),
                'time_seconds': round(route_time),
                'time_minutes': round(route_time / 60, 1),
                'student_count': len(route_students),
                'segments': route_segments,  # Raw segments, no geometry yet
                'departure_time': format_time(actual_departure_time),
                'arrival_time': format_time(school_arrival_time),
                'vehicle_index': original_vehicle_index # Maps back to specific fleet vehicle
            })
            
            total_distance += route_distance
            max_route_time = max(max_route_time, route_time)
    
    if time_violations:
        print(f"\nTIME VIOLATIONS:")
        for v in time_violations:
            print(f"   {v['student']} on Bus {v['bus']}: {v['ride_minutes']} min (limit: {max_ride_time_minutes} min)")
    
    print(f"CVRP solved! {len(routes)} routes, Total distance: {total_distance:.2f} km")
    print(f"Max student ride time: {max_student_ride_time/60:.1f} minutes")
    
    return {
        'routes': routes,
        'total_distance': total_distance,
        'max_route_time': max_route_time,
        'num_buses': len(routes),
        'max_student_ride_time': max_student_ride_time,
        'time_violations': time_violations
    }


def enrich_routes_with_geometry(routes: List[Dict], api_key: str,
                                 school_arrival_time: int, max_ride_time_minutes: int,
                                 service_time: int = 60) -> List[Dict]:
    """
    Post-processing: fetch real road geometry for all routes.
    Called after solve_cvrp returns, not inside the solving loop.
    Also recalculates pickup times and ride durations with real data.

    `service_time` should mirror the value used by the solver.
    """
    print(f"\n=== Fetching road geometry for {len(routes)} route(s) ===")

    for route in routes:
        segments = route.get('segments', [])
        if not segments:
            continue

        enriched_segments = get_real_route_geometry_for_segments(segments, api_key)

        # Recalculate with real distances. Dwell time mirrors the solver's
        # super-node model (route_optimizer.py:769): first student at each
        # pickup address costs `service_time`, each sibling at the same
        # address costs +15s. Counting N*service_time over-charges siblings.
        real_distance = sum(seg.get('distance', 0) for seg in enriched_segments)
        real_travel_time = sum(seg.get('time', 0) for seg in enriched_segments)

        students_in_order = route['students']
        distinct_locs = {
            (round(s['latitude'], 5), round(s['longitude'], 5))
            for s in students_in_order
        }
        num_stops = len(distinct_locs)
        num_students = len(students_in_order)
        total_dwell = num_stops * service_time + (num_students - num_stops) * 15

        real_time = real_travel_time + total_dwell
        actual_departure_time = school_arrival_time - int(real_time)

        # Walk students in solver order. Segments list is super-node-aligned
        # (S1->S2, ..., S_{K-1}->S_K, S_K->school) — no school->S1 leg
        # (OVRP-zeroed). Consume one inbound segment each time the pickup
        # address changes; siblings at the same address share the segment.
        cumulative_real_time = 0
        time_violations = []
        max_student_ride_time = 0
        prev_loc = None
        seg_idx = 0

        for student_data in students_in_order:
            cur_loc = (round(student_data['latitude'], 5), round(student_data['longitude'], 5))
            if cur_loc != prev_loc:
                if prev_loc is not None and seg_idx < len(enriched_segments):
                    cumulative_real_time += enriched_segments[seg_idx].get('time', 0)
                    seg_idx += 1
                actual_pickup_time = actual_departure_time + cumulative_real_time
                cumulative_real_time += service_time
            else:
                actual_pickup_time = actual_departure_time + cumulative_real_time
                cumulative_real_time += 15

            ride_duration = school_arrival_time - actual_pickup_time
            student_data['pickup_time'] = format_time(int(actual_pickup_time))
            student_data['ride_duration_minutes'] = round(ride_duration / 60, 1)
            max_student_ride_time = max(max_student_ride_time, ride_duration)

            if ride_duration > max_ride_time_minutes * 60:
                time_violations.append({
                    'student': student_data.get('name', 'Unknown'),
                    'ride_minutes': round(ride_duration / 60, 1),
                    'bus': route.get('bus_number', 0)
                })
            prev_loc = cur_loc
        
        # Preserve old haversine values before overwriting
        if 'haversine_time_minutes' not in route:
            route['haversine_time_minutes'] = route.get('time_minutes')
            route['haversine_distance_km'] = route.get('distance_km')

        # Update route with real data
        route['segments'] = enriched_segments
        route['distance_km'] = round(real_distance, 2)
        route['time_seconds'] = round(real_time)
        route['time_minutes'] = round(real_time / 60, 1)
        route['departure_time'] = format_time(actual_departure_time)
        if time_violations:
            route['time_violations'] = time_violations
    
    # Save cache once after all geometry is fetched
    save_cache_to_file()
    print("Road geometry enrichment complete. Cache saved.")
    
    return routes


def optimize_routes(school: Dict, students: List[Dict], max_buses: int, api_key: str,
                    school_arrival_time: int = 27000, max_ride_time: int = 60,
                    fleet_capacities: List[int] = None, advanced_params: Dict = None) -> Dict:
    # Reset API health flag in case the key was updated
    # Cache is preserved across runs — only invalidated when school changes
    global _api_healthy
    _api_healthy = True

    if advanced_params is None:
        advanced_params = {
            'service_time': 60,
            'base_bus_cost': 5000,
            'penalty_per_seat': 200
        }
    print(f"Optimize Routes: API Key Prefix: {api_key[:10]}... Len: {len(api_key)}")

    """
    Optimize bus routes using Google OR-Tools CVRP solver
    
    Strategy:
    1. Validate all inputs
    2. Analyze student distribution for visualization only
    3. Let CVRP handle all routing (it already does multi-vehicle optimization)
    4. Try different bus counts and pick the best (no violations)
    """
    # ===== INPUT VALIDATION =====
    if not school or not students:
        return {
            'routes': [],
            'total_buses': 0,
            'error': 'School location or students not set'
        }

    # Debug Data Validity
    print(f"DEBUG: School Location: {school}")
    if students:
        print(f"DEBUG: First 3 Students: {students[:3]}")
        # Check for zero coordinates
        zeros = [s for s in students if s.get('lat') == 0 or s.get('lng') == 0]
        if zeros:
            print(f"WARNING: Found {len(zeros)} students with 0.0 coordinates!")
    else:
        print("DEBUG: No students!")
    
    # Validate max_buses
    if not isinstance(max_buses, int) or max_buses < 1:
        return {
            'routes': [],
            'total_buses': 0,
            'error': f'Invalid max_buses: {max_buses}. Must be a positive integer >= 1'
        }
    
    # Validate API key
    if not api_key or not isinstance(api_key, str) or len(api_key.strip()) == 0:
        return {
            'routes': [],
            'total_buses': 0,
            'error': 'Invalid or missing API key'
        }
    
    # Validate school coordinates
    try:
        school_lat = float(school.get('latitude'))
        school_lng = float(school.get('longitude'))
        if not (-90 <= school_lat <= 90) or not (-180 <= school_lng <= 180):
            raise ValueError("School coordinates out of valid range")
    except (TypeError, ValueError, KeyError) as e:
        return {
            'routes': [],
            'total_buses': 0,
            'error': f'Invalid school coordinates: {e}'
        }
    
    # Validate student coordinates
    for i, student in enumerate(students):
        try:
            lat = float(student.get('latitude'))
            lng = float(student.get('longitude'))
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                raise ValueError(f"Coordinates out of valid range")
        except (TypeError, ValueError, KeyError) as e:
            return {
                'routes': [],
                'total_buses': 0,
                'error': f'Invalid coordinates for student at index {i} ({student.get("name", "unknown")}): {e}'
            }
    
    # ===== CACHE INVALIDATION =====
    # CRITICAL: Clear cache if school location changed to avoid wrong routes
    invalidate_cache_if_school_changed(school)

    # Check if this is a large dataset that requires divide-and-conquer
    is_large_dataset = len(students) >= 60

    # ===== FLEET AWARE OPTIMIZATION =====
    if fleet_capacities and len(fleet_capacities) > 0 and not is_large_dataset:
        print(f"!!! USING HETEROGENEOUS FLEET !!!")
        print(f"Vehicles: {len(fleet_capacities)}, Capacities: {fleet_capacities}")

        result = solve_cvrp(school, students, len(fleet_capacities), api_key,
                           school_arrival_time=school_arrival_time,
                           max_ride_time_minutes=max_ride_time,
                           vehicle_capacities=fleet_capacities,
                           advanced_params=advanced_params)

        if 'error' in result or not result.get('routes'):
            error_msg = result.get('error', 'No feasible solution found with hard time constraint')

            return {
                'routes': [],
                'total_buses': 0,
                'error': error_msg,
                'current_fleet_size': len(fleet_capacities)
            }

        all_violations = []
        for route in result['routes']:
            if route.get('time_violations'):
                all_violations.extend(route['time_violations'])

        if all_violations:
            print(f"WARNING: {len(all_violations)} time violation(s) detected after geometry enrichment")
            result['time_violations'] = all_violations
            result['optimization_note'] = f"Warning: {len(all_violations)} student(s) exceed {max_ride_time}-minute ride time after real road calculation"

        return result

    # ===== FEASIBILITY CHECK =====
    min_buses_needed = max(1, math.ceil(len(students) / 40))

    if max_buses < min_buses_needed:
        return {
            'routes': [],
            'total_buses': 0,
            'error': f'Infeasible: {len(students)} students require at least {min_buses_needed} bus(es) '
                     f'(capacity: 40 students/bus), but max_buses is set to {max_buses}. '
                     f'Please increase max_buses to at least {min_buses_needed}.',
        }

    if min_buses_needed > max_buses:
        print(f"WARNING: Math requires at least {min_buses_needed} buses but max is {max_buses}.")
        print(f"         Will attempt optimization with {max_buses} buses - may have time violations.")

    return _solve_unified(
        school, students, max_buses, api_key,
        min_buses_needed, school_arrival_time, max_ride_time,
        advanced_params=advanced_params
    )


def _solve_unified(school: Dict, students: List[Dict], max_buses: int, api_key: str,
                   min_buses_needed: int,
                   school_arrival_time: int = 27000, max_ride_time: int = 60,
                   advanced_params: Dict = None) -> Dict:
    """
    Unified approach: all students go to single CVRP solver.
    Uses SetFixedCostOfVehicle to minimize buses in a single run.
    """
    print(f"Solving with up to {max_buses} bus(es)\n")

    result = solve_cvrp(school, students, max_buses, api_key,
                        school_arrival_time=school_arrival_time,
                        max_ride_time_minutes=max_ride_time,
                        advanced_params=advanced_params)

    if 'error' in result or not result['routes']:
        error_msg = result.get('error', 'No feasible solution found with hard time constraint')

        return {
            'routes': [],
            'total_buses': 0,
            'error': error_msg,
        }

    all_violations = []
    for route in result['routes']:
        if route.get('time_violations'):
            all_violations.extend(route['time_violations'])

    if all_violations:
        print(f"WARNING: {len(all_violations)} time violation(s) after geometry enrichment")
        return {
            'routes': result['routes'],
            'total_buses': result['num_buses'],
            'max_route_time_minutes': round(result['max_route_time'] / 60, 1),
            'max_student_ride_time_minutes': round(result.get('max_student_ride_time', 0) / 60, 1),
            'total_distance_km': round(result['total_distance'], 2),
            'optimization_note': f"Warning: {len(all_violations)} student(s) exceed {max_ride_time}-minute ride time after real road calculation",
            'time_violations': all_violations,
            'routing_strategy': 'unified_with_violations'
        }

    selection_note = f"Optimal: {result['num_buses']} bus(es) - all routes within {max_ride_time} min"
    print(f"Optimal: {result['num_buses']} bus(es)")

    return {
        'routes': result['routes'],
        'total_buses': result['num_buses'],
        'max_route_time_minutes': round(result['max_route_time'] / 60, 1),
        'max_student_ride_time_minutes': round(result.get('max_student_ride_time', 0) / 60, 1),
        'total_distance_km': round(result['total_distance'], 2),
        'optimization_note': selection_note,
        'routing_strategy': 'unified_optimized'
    }




def recalculate_manually_adjusted_routes(routes: List[Dict], school: Dict, api_key: str,
                                         school_arrival_time: int = 27000, max_ride_time_minutes: int = 60,
                                         service_time: int = 60) -> List[Dict]:
    """
    Recalculates times and distances for manually modified routes (e.g. from drag & drop).
    Applies 2-opt reordering to the students to ensure optimal pickup order.
    """
    recalculated_routes = []
    
    for route in routes:
        students = route.get('students', [])
        if not students:
            continue
            
        # --- 2-Opt Reordering (Super Node aware) ---
        # 1. Build a local distance matrix for just this route's students + school
        local_matrix, _ = build_distance_and_time_matrices_real(school, students)
        
        # 2. Build route indices for 2-opt: [0 (school), 1, 2, 3, ..., N, 0]
        # (Using indices 1 to N matching the local_matrix)
        route_indices = [0] + list(range(1, len(students) + 1)) + [0]
        
        # 3. Apply 2-opt algorithm
        optimized_indices, _ = two_opt(route_indices, local_matrix)
        
        # 4. Map indices back to students
        # Ignore the first and last element (which are 0 for the depot)
        optimized_students = []
        for idx in optimized_indices[1:-1]:
            # Remember local_matrix index 1 corresponds to students[0]
            optimized_students.append(students[idx - 1])
            
        students = optimized_students
        # Update the route dict with optimized students
        route['students'] = students
        # -------------------------------------------

        new_route = route.copy()
        segments = []
        
        # Build segments list: S1->S2, S2->S3, Sn->School
        for i in range(len(students) - 1):
            s1 = students[i]
            s2 = students[i+1]
            segments.append({
                'from': {'lat': s1['latitude'], 'lng': s1['longitude']},
                'to': {'lat': s2['latitude'], 'lng': s2['longitude']},
                'student': s2.get('name', s2.get('Name', 'Unknown'))
            })
            
        # Add return to school segment
        last_s = students[-1]
        segments.append({
            'from': {'lat': last_s['latitude'], 'lng': last_s['longitude']},
            'to': {'lat': school['latitude'], 'lng': school['longitude']},
            'student': 'Return to School'
        })
        
        # Use existing geometry fetcher
        enriched_segments = get_real_route_geometry_for_segments(segments, api_key)

        real_travel_time = 0
        real_distance = 0
        for seg in enriched_segments:
            real_travel_time += seg.get('time', 0)
            real_distance += seg.get('distance', 0)

        # Dwell time mirrors solver's super-node model: first student at each
        # pickup address costs `service_time`, each sibling at the same
        # address costs +15s.
        distinct_locs = {
            (round(s['latitude'], 5), round(s['longitude'], 5)) for s in students
        }
        num_stops = len(distinct_locs)
        total_dwell = num_stops * service_time + (len(students) - num_stops) * 15
        real_time = real_travel_time + total_dwell

        # Calculate backward from school arrival to get individual pickup times
        actual_departure_time = school_arrival_time - real_time
        cumulative_real_time = 0
        time_violations = []
        max_student_ride_time = 0

        # The school -> first student segment cost is 0 in CVRP,
        # so ride time starts at the first pickup. Segments here are built
        # per-student (S1->S2, S2->S3, ..., Sn->school); siblings at the
        # same address have a zero-time stub segment between them.
        prev_loc = None
        for i, s_data in enumerate(students):
            if i > 0 and (i - 1) < len(enriched_segments):
                cumulative_real_time += enriched_segments[i - 1].get('time', 0)

            cur_loc = (round(s_data['latitude'], 5), round(s_data['longitude'], 5))
            actual_pickup_time = actual_departure_time + cumulative_real_time
            ride_duration = school_arrival_time - actual_pickup_time

            if cur_loc == prev_loc:
                cumulative_real_time += 15
            else:
                cumulative_real_time += service_time

            s_data['pickup_time'] = format_time(int(actual_pickup_time))
            s_data['ride_duration_minutes'] = round(ride_duration / 60, 1)

            max_student_ride_time = max(max_student_ride_time, ride_duration)

            # Use special_needs specific limit if applicable
            time_limit = 30 * 60 if s_data.get('special_needs') else max_ride_time_minutes * 60
            if ride_duration > time_limit:
                time_violations.append({
                    'student': s_data.get('name', 'Unknown'),
                    'ride_minutes': round(ride_duration / 60, 1),
                    'bus': new_route.get('bus_number', 0)
                })
            prev_loc = cur_loc
                
        new_route['segments'] = enriched_segments
        new_route['distance_km'] = round(real_distance, 2)
        new_route['time_seconds'] = round(real_time)
        new_route['time_minutes'] = round(real_time / 60, 1)
        new_route['departure_time'] = format_time(int(actual_departure_time))
        new_route['time_violations'] = time_violations
        new_route['max_ride_minutes'] = round(max_student_ride_time / 60, 1)

        recalculated_routes.append(new_route)

    save_cache_to_file()
    return recalculated_routes


def recalculate_routes_for_verification(routes: List[Dict],
                                        school: Dict,
                                        school_arrival_time: int,
                                        max_ride_time_minutes: int,
                                        service_time: int = 60) -> List[Dict]:
    """Fast variant of recalculate_manually_adjusted_routes for AI-Refine
    verification. Skips per-segment polyline fetching (the slow part — 530+
    NetworkX Dijkstras for 41 buses) by reading time/distance directly from
    the same igraph-based matrix the solver uses. Suitable for hard-constraint
    checks and delta computation. Polylines only matter when the user actually
    applies a suggestion, so apply_suggestion still uses the full recalc."""
    out = []
    for route in routes:
        students = route.get('students', [])
        if not students:
            continue

        # 1. Build matrix (fast — igraph)
        dist_m, time_s = build_distance_and_time_matrices_real(school, students)

        # 2. 2-opt reorder using the distance matrix
        route_indices = [0] + list(range(1, len(students) + 1)) + [0]
        optimized_indices, _ = two_opt(route_indices, dist_m)
        students = [students[i - 1] for i in optimized_indices[1:-1]]
        new_route = route.copy()
        new_route['students'] = students

        # 3. Sum segment times/distances from matrix instead of polyline fetch.
        # Sequence is: school(0) -> s1 -> s2 -> ... -> sn -> school(0).
        # Solver convention: school -> first student segment is free for OVRP,
        # which mirrors what recalculate_manually_adjusted_routes does (it
        # uses i-1 indexing into segments starting at i>0, so the first
        # student's pickup time = departure time + 0).
        n = len(students)
        seg_times = []   # times[i] = travel s[i] -> s[i+1] (or last -> school)
        seg_dists = []
        for i in range(n - 1):
            mi = i + 1
            mj = i + 2
            seg_times.append(time_s[mi][mj])
            seg_dists.append(dist_m[mi][mj])
        # last student -> school
        seg_times.append(time_s[n][0])
        seg_dists.append(dist_m[n][0])

        real_travel_time = sum(seg_times)
        real_distance_m = sum(seg_dists)

        # Dwell time mirrors recalculate_manually_adjusted_routes / solver
        distinct_locs = {
            (round(s['latitude'], 5), round(s['longitude'], 5)) for s in students
        }
        num_stops = len(distinct_locs)
        total_dwell = num_stops * service_time + (len(students) - num_stops) * 15
        real_time = real_travel_time + total_dwell

        actual_departure_time = school_arrival_time - real_time
        cumulative_real_time = 0
        time_violations = []
        max_student_ride_time = 0
        prev_loc = None
        for i, s_data in enumerate(students):
            if i > 0:
                cumulative_real_time += seg_times[i - 1]

            cur_loc = (round(s_data['latitude'], 5), round(s_data['longitude'], 5))
            actual_pickup_time = actual_departure_time + cumulative_real_time
            ride_duration = school_arrival_time - actual_pickup_time

            if cur_loc == prev_loc:
                cumulative_real_time += 15
            else:
                cumulative_real_time += service_time

            s_data['pickup_time'] = format_time(int(actual_pickup_time))
            s_data['ride_duration_minutes'] = round(ride_duration / 60, 1)
            max_student_ride_time = max(max_student_ride_time, ride_duration)

            time_limit = 30 * 60 if s_data.get('special_needs') else max_ride_time_minutes * 60
            if ride_duration > time_limit:
                time_violations.append({
                    'student': s_data.get('name', 'Unknown'),
                    'ride_minutes': round(ride_duration / 60, 1),
                })
            prev_loc = cur_loc

        new_route['time_minutes'] = round(real_time / 60, 1)
        new_route['distance_km'] = round(real_distance_m / 1000, 2)
        new_route['departure_time'] = format_time(int(actual_departure_time))
        new_route['time_violations'] = time_violations
        new_route['max_ride_minutes'] = round(max_student_ride_time / 60, 1)
        out.append(new_route)

    save_cache_to_file()
    return out
