"""
Route optimization algorithm for school bus routing
Uses Google OR-Tools CVRP solver with real driving distances
Includes smart density-based pre-clustering for bus allocation
"""
import math
import json
import os
from typing import List, Dict, Tuple
import requests
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import numpy as np
from sklearn.cluster import DBSCAN
import time
from threading import Lock
  
# Cache file path (in same directory as this script)
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'route_cache.json')
MAX_CACHE_ENTRIES = 5000  # Limit cache size to prevent file from growing too large

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


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers"""
    R = 6371  # Earth's radius in km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    distance_km = R * c
    return distance_km


def estimate_travel_time(distance_km: float) -> float:
    """Estimate travel time in seconds based on distance
    Uses 50 km/h average speed for Singapore school bus routes
    """
    avg_speed_kmh = 50
    time_hours = distance_km / avg_speed_kmh
    return time_hours * 3600  # convert to seconds


def get_route_from_onemap(start_lat: float, start_lng: float, end_lat: float, end_lng: float, api_key: str, max_retries: int = 3) -> Tuple[float, float, List]:
    """
    Get actual route distance, time, and geometry from OneMap routing API
    Includes caching, retry logic, and rate limiting.
    Skips API entirely if a previous call returned 401/403 (expired key).
    """
    global last_api_call_time, _api_healthy, postal_code_cache
    
    # Create cache key (round to 4 decimal places for ~11m precision)
    cache_key = f"{start_lat:.4f},{start_lng:.4f}->{end_lat:.4f},{end_lng:.4f}"
    
    # Check cache first
    if cache_key in distance_cache:
        # print(f"  Cache hit: {cache_key}")
        return distance_cache[cache_key]

    print(f"  API Fetch: {cache_key} | Healthy: {_api_healthy}")
    
    # Skip API if a previous call already failed with auth error
    if not _api_healthy:
        distance = haversine_distance(start_lat, start_lng, end_lat, end_lng)
        time_est = estimate_travel_time(distance)
        geometry = [[start_lat, start_lng], [end_lat, end_lng]]
        result = (distance, time_est, geometry)
        distance_cache[cache_key] = result
        return result
    
    # Rate limiting
    with rate_limit_lock:
        elapsed = time.time() - last_api_call_time
        if elapsed < MIN_API_INTERVAL:
            time.sleep(MIN_API_INTERVAL - elapsed)
        last_api_call_time = time.time()
    
    # Try API with retry logic
    for attempt in range(max_retries):
        try:
            url = "https://www.onemap.gov.sg/api/public/routingsvc/route"
            params = {
                'start': f"{start_lat},{start_lng}",
                'end': f"{end_lat},{end_lng}",
                'routeType': 'drive'
            }
            headers = {'Authorization': api_key}
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 0 and 'route_summary' in data:
                    # Distance in meters, time in seconds
                    distance_m = data['route_summary']['total_distance']
                    time_s = data['route_summary']['total_time']
                    
                    # Decode route geometry
                    geometry = decode_polyline(data['route_geometry'])
                    
                    result = (distance_m / 1000, time_s, geometry)
                    
                    # Cache the result (batch-saved later, not per-call)
                    distance_cache[cache_key] = result
                    print(f"  API success: {distance_m}m, {len(geometry)} pts. First: {geometry[0] if geometry else 'None'}")
                    
                    return result
            else:
                print(f"  API FAIL: Status {response.status_code}. Response: {response.text[:200]}")
            
            # If we get here, API returned non-200 or invalid data
            if response.status_code in (401, 403):
                # Auth failure — don't retry, mark API as unhealthy
                print(f"  API auth failed ({response.status_code}) — switching to haversine for all remaining calls")
                _api_healthy = False
                break
            
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"  Retry ({attempt + 1}/{max_retries}): status {response.status_code}")
                time.sleep(wait_time)
            
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"  Retry ({attempt + 1}/{max_retries}): timeout")
                time.sleep(wait_time)
            else:
                print(f"  Failed: timeout after {max_retries} attempts")
        
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"  Retry ({attempt + 1}/{max_retries}): {e}")
                time.sleep(wait_time)
            else:
                print(f"  Failed after {max_retries} attempts: {e}")
                # Log detailed error for debugging
                print(f"  DEBUG FAILURE: {cache_key} -> {e}")
    
    # Fallback to haversine estimation with straight line
    print(f"  Fallback to haversine: {cache_key}")
    distance = haversine_distance(start_lat, start_lng, end_lat, end_lng)
    time_est = estimate_travel_time(distance)
    geometry = [[start_lat, start_lng], [end_lat, end_lng]]
    
    result = (distance, time_est, geometry)
    
    # Cache the fallback result too
    distance_cache[cache_key] = result
    
    return result


def decode_polyline(encoded: str) -> List[List[float]]:
    """Decode OneMap polyline format to lat/lng coordinates"""
    try:
        coordinates = []
        index = 0
        lat = 0
        lng = 0
        
        while index < len(encoded):
            # Decode latitude
            result = 0
            shift = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            dlat = ~(result >> 1) if (result & 1) else (result >> 1)
            lat += dlat
            
            # Decode longitude
            result = 0
            shift = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            dlng = ~(result >> 1) if (result & 1) else (result >> 1)
            lng += dlng
            
            coordinates.append([lat / 1e5, lng / 1e5])
        
        return coordinates
    except:
        return []


def build_distance_matrix_fast(school: Dict, students: List[Dict]) -> List[List[int]]:
    """
    Build distance matrix using haversine with adaptive road factor
    FAST: No API calls, instant calculation
    Returns: distance_matrix in meters
    """
    points = [school] + students
    n = len(points)
    distance_matrix = [[0] * n for _ in range(n)]
    
    print(f"Building distance matrix for {n} points (haversine)...")
    
    for i in range(n):
        for j in range(i + 1, n):
            # Calculate straight-line distance in km
            distance_km = haversine_distance(
                points[i]['latitude'], points[i]['longitude'],
                points[j]['latitude'], points[j]['longitude']
            )
            
            # Adaptive road factor based on distance
            # INCREASED IMPACT: Real roads are much slower than Haversine
            # Short distances (<2km): 2.0x (dense urban, many turns, traffic lights)
            # Medium distances (2-10km): 1.6x (suburban)
            # Long distances (>10km): 1.4x (highways)
            if distance_km < 2:
                road_factor = 2.0
            elif distance_km < 10:
                road_factor = 1.6
            else:
                road_factor = 1.4
            
            # Convert to meters for OR-Tools
            distance_m = int(distance_km * road_factor * 1000)
            
            distance_matrix[i][j] = distance_m
            distance_matrix[j][i] = distance_m
    
    print("Distance matrix built")
    return distance_matrix


def get_real_route_geometry_for_segments(route_segments: List[Dict], api_key: str) -> List[Dict]:
    """
    Get real road geometry from OneMap for route segments
    Called AFTER optimization to display real roads on map
    Uses parallel processing for speed
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    print(f"Fetching road geometry for {len(route_segments)} segments...")
    
    def fetch_segment(segment):
        try:
            # Debug: Print keys to see what we actually have
            # print(f"DEBUG Seg: from keys={list(segment['from'].keys())}", flush=True)
            
            p_from = segment['from']
            p_to = segment['to']
            
            from_lat = p_from.get('lat') or p_from.get('latitude')
            from_lng = p_from.get('lng') or p_from.get('longitude')
            to_lat = p_to.get('lat') or p_to.get('latitude')
            to_lng = p_to.get('lng') or p_to.get('longitude')
            
            if not from_lat or not from_lng or not to_lat or not to_lng:
                print(f"  SEGMENT ERROR: Missing coords! From: {p_from}, To: {p_to}", flush=True)
                raise ValueError("Missing coordinates")

            # Get real route from OneMap
            distance_km, time_s, geometry = get_route_from_onemap(
                from_lat, from_lng, to_lat, to_lng, api_key
            )
            
            # VALIDATION: Check for major distance mismatch
            hav_dist = haversine_distance(from_lat, from_lng, to_lat, to_lng)
            if hav_dist > 0.5 and abs(distance_km - hav_dist) > 5.0:
                print(f"  WARNING: Major distance mismatch! Seg: {segment.get('student', 'Unknown')}")
                print(f"    Req: {from_lat},{from_lng} -> {to_lat},{to_lng}")
                print(f"    Haversine: {hav_dist:.2f}km, API: {distance_km:.2f}km")
                print(f"    Geometry pts: {len(geometry)}")
                if geometry:
                    first_pt = geometry[0]
                    last_pt = geometry[-1]
                    start_diff = haversine_distance(from_lat, from_lng, first_pt[0], first_pt[1])
                    end_diff = haversine_distance(to_lat, to_lng, last_pt[0], last_pt[1])
                    print(f"    Start Diff: {start_diff:.2f}km, End Diff: {end_diff:.2f}km")
            
            # Update segment with real data
            segment['geometry'] = geometry
            segment['distance'] = distance_km
            segment['time'] = time_s
            
            return segment
        except Exception as e:
            print(f"  FETCH SEGMENT EXCEPTION: {e}", flush=True)
            raise e
    
    # Parallel API calls (max 5 concurrent to avoid rate limits)
    enriched_segments = [None] * len(route_segments)
    # Use sequential execution (max_workers=1) to prevent race conditions and improve debugging
    with ThreadPoolExecutor(max_workers=1) as executor:
        future_to_idx = {executor.submit(fetch_segment, seg): idx 
                        for idx, seg in enumerate(route_segments)}
        
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                enriched_segments[idx] = future.result()
            except Exception as e:
                print(f"  Segment {idx} failed: {e}")
                # Keep original segment if API fails
                enriched_segments[idx] = route_segments[idx]
    
    print("Road geometry fetched")
    return enriched_segments

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


def build_distance_matrix_parallel(school: Dict, students: List[Dict], api_key: str) -> List[List[int]]:
    """
    Build distance matrix with parallel API calls for REAL driving distances.
    Uses ThreadPoolExecutor for 5-10x speed improvement.
    Falls back to haversine for failed API calls.
    Returns: distance_matrix in meters
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    points = [school] + students
    n = len(points)
    distance_matrix = [[0] * n for _ in range(n)]
    
    print(f"Building distance matrix for {n} points (parallel API)...")
    
    # Collect all pairs that need distance calculation
    pairs_to_fetch = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs_to_fetch.append((i, j))
    
    total_pairs = len(pairs_to_fetch)
    completed = [0]  # Use list to allow mutation in nested function
    cache_hits = [0]
    api_calls = [0]
    
    def fetch_distance(pair):
        i, j = pair
        start_lat = points[i]['latitude']
        start_lng = points[i]['longitude']
        end_lat = points[j]['latitude']
        end_lng = points[j]['longitude']
        
        # Check cache first (this is done inside get_route_from_onemap but we track it)
        cache_key = f"{start_lat:.4f},{start_lng:.4f}->{end_lat:.4f},{end_lng:.4f}"
        if cache_key in distance_cache:
            cache_hits[0] += 1
        else:
            api_calls[0] += 1
        
        # Get distance (uses cache or API)
        distance_km, time_s, _ = get_route_from_onemap(
            start_lat, start_lng, end_lat, end_lng, api_key
        )
        
        completed[0] += 1
        if completed[0] % 10 == 0:
            print(f"  Progress: {completed[0]}/{total_pairs} ({cache_hits[0]} cached)")
        
        return (i, j, int(distance_km * 1000))  # Return distance in meters
    
    # Parallel execution with max_workers=5 to respect API rate limits
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_distance, pair): pair for pair in pairs_to_fetch}
        
        for future in as_completed(futures):
            try:
                i, j, distance_m = future.result()
                distance_matrix[i][j] = distance_m
            except Exception as e:
                pair = futures[future]
                i, j = pair
                # Fallback to haversine
                # points[0] is the school, points[1:] are students
                # If i or j is 0 (school), we need to handle it.
                # The instruction is to set school-to-student distances to 0 for OVRP logic.
                # This is typically handled in the CVRP model's cost callback,
                # but if the underlying matrix needs to reflect this for some reason,
                # we can apply it here. However, the `_build_cvrp_model` already handles this
                # in its `distance_callback`.
                # If the intent is to modify the *raw* distance_matrix itself,
                # then for (0, j) or (i, 0) pairs, we need special handling.
                # The provided snippet for the change is syntactically incorrect for this function.
                # Assuming the intent is to ensure the distance matrix itself reflects this
                # for the purpose of the fallback, we'll apply the OVRP logic here.
                if i == 0 and j > 0: # School to student
                    distance_m = 0
                elif j == 0 and i > 0: # Student to school (return trip, should be real)
                    distance_km = haversine_distance(
                        points[i]['latitude'], points[i]['longitude'],
                        points[j]['latitude'], points[j]['longitude']
                    )
                    distance_m = int(distance_km * 1.35 * 1000) # Apply road factor
                else: # Student to student
                    distance_km = haversine_distance(
                        points[i]['latitude'], points[i]['longitude'],
                        points[j]['latitude'], points[j]['longitude']
                    )
                    distance_m = int(distance_km * 1.35 * 1000) # Apply road factor

                distance_matrix[i][j] = distance_m
                distance_matrix[j][i] = distance_m # Symmetric matrix
                print(f"  Pair ({i},{j}) fallback: {e}")
    
    # OPEN VRP MODIFICATION: Ensure distance FROM School (0) TO any Student (j) is 0
    # This allows the route to start at any student without "cost" from depot.
    # The `_build_cvrp_model`'s `distance_callback` already handles this,
    # but explicitly setting it here ensures the raw matrix also reflects it if needed elsewhere.
    for j in range(1, n): # For all students (j > 0)
        distance_matrix[0][j] = 0
    
    print(f"Distance matrix built ({cache_hits[0]} cached, {api_calls[0]} API calls)")
    return distance_matrix


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
                       vehicle_capacities: List[int] = None):
    """
    Build and return a CVRP model (manager, routing, callbacks) without solving.
    Shared by both Phase 1 and Phase 2 of two-phase solving.
    """
    manager = pywrapcp.RoutingIndexManager(
        len(distance_matrix), num_vehicles, 0
    )
    routing = pywrapcp.RoutingModel(manager)
    
    # Distance callback (open-ended: school→student cost = 0)
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
        return 1 if from_node > 0 else 0
    
    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index, 0, capacities, True, 'Capacity'
    )

    # CAPACITY UTILIZATION PENALTY: Penalize wasted seats (unused capacity)
    # Strategy: Set soft upper bound at vehicle capacity with penalty
    # This encourages filling the bus as close to capacity as possible
    capacity_dimension = routing.GetDimensionOrDie('Capacity')
    PENALTY_PER_EMPTY_SEAT = 100  # Cost per wasted seat - encourages using smaller buses

    for vehicle_id in range(num_vehicles):
        end_index = routing.End(vehicle_id)
        vehicle_capacity = capacities[vehicle_id]
        # Soft upper bound at capacity - but we want to encourage filling it
        # Actually, we need to penalize the GAP between actual and capacity
        # OR-Tools way: Set soft upper bound high and penalize not reaching it
        # Alternative: Set slack cost on the capacity dimension

        # Better approach: Use soft lower bound behavior indirectly
        # By setting a high target and penalizing deviations, we encourage full utilization
        # But OR-Tools doesn't have soft lower bound, so we invert:

        # Set soft upper bound at a very high value (1000 students)
        # The penalty applies when exceeding, not when under
        # So this doesn't work for penalizing under-utilization...

        # CORRECT APPROACH for OR-Tools:
        # Penalize routes that don't use their full capacity
        # By setting soft upper bound at vehicle_capacity with penalty,
        # solver gets penalized if students exceed capacity (hard constraint violation)
        # But we want penalty for NOT filling...

        # Actually, the best way: minimize slack by setting soft upper bound
        # on the cumulative value to encourage higher values
        # We do this by setting target = capacity, and penalize going over (which is invalid anyway)
        # The key insight: this doesn't directly penalize under-utilization

        # WORKAROUND: Use a different dimension or modify the fixed cost
        # based on capacity utilization - but that's post-solve

        # SIMPLER APPROACH: Reduce fixed cost for smaller buses
        # This makes smaller buses cheaper to use, so solver prefers them
        pass  # Will use alternative approach below

    # ALTERNATIVE: Variable fixed cost based on bus size
    # Smaller buses are cheaper to use, so solver prefers them when possible
    # Large buses only used when capacity is actually needed
    VEHICLE_FIXED_COST_BASE = 20000
    for vehicle_id in range(num_vehicles):
        vehicle_capacity = capacities[vehicle_id]
        # Smaller buses have lower fixed cost
        # Cost = base - (capacity savings)
        # 45-seater: 20000, 25-seater: 15000 (saves 5000 for using smaller bus)
        capacity_penalty = (vehicle_capacity - 20) * 200  # Larger buses cost more
        fixed_cost = VEHICLE_FIXED_COST_BASE + capacity_penalty
        routing.SetFixedCostOfVehicle(fixed_cost, vehicle_id)

    # Time constraint
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        if from_node == 0 and to_node > 0:
            return 60
        distance_m = distance_matrix[from_node][to_node]
        travel_time = estimate_travel_time(distance_m / 1000)
        pickup_time = 60 if to_node > 0 else 0
        return int(travel_time + pickup_time)
    
    time_callback_index = routing.RegisterTransitCallback(time_callback)
    
    max_ride_seconds = int(max_ride_time_minutes * 60)

    # HARD CONSTRAINT: Time limit is strict, not soft
    # Routes MUST be under the max_ride_time limit
    # If infeasible with available fleet, solver will return no solution
    max_hard_cap = max_ride_seconds  # Strict hard cap - no violations allowed

    routing.AddDimension(
        time_callback_index, slack_max=1800, capacity=max_hard_cap,
        fix_start_cumul_to_zero=True, name='Time'
    )

    time_dimension = routing.GetDimensionOrDie('Time')

    # No soft upper bound needed - hard cap enforces the limit
    # Global span cost to minimize route duration spread
    time_dimension.SetGlobalSpanCostCoefficient(200)
    
    VEHICLE_FIXED_COST = 20000
    for vehicle_id in range(num_vehicles):
        routing.SetFixedCostOfVehicle(VEHICLE_FIXED_COST, vehicle_id)
    
    return manager, routing, capacities


def solve_cvrp(school: Dict, students: List[Dict], num_vehicles: int, api_key: str, 
               max_route_time_minutes: int = 60,
               school_arrival_time: int = 27000,
               max_ride_time_minutes: int = 60,
               vehicle_capacities: List[int] = None) -> Dict:
    """
    Two-Phase CVRP solver:
      Phase 1 (5s): Quick solve with max vehicles → discover optimal bus count
      Phase 2 (15s): Re-solve with exact bus count → better route quality
    """
    if not students:
        return {'routes': [], 'total_distance': 0, 'total_time': 0}
    
    distance_matrix = build_distance_matrix_fast(school, students)
    
    # ===== PHASE 1: Quick solve to discover bus count (5 seconds) =====
    print(f"\n--- Phase 1: Quick solve with {num_vehicles} vehicles (5s) ---")
    manager, routing, capacities = _build_cvrp_model(
        school, students, num_vehicles, distance_matrix,
        max_ride_time_minutes, vehicle_capacities
    )
    
    search_params_p1 = pywrapcp.DefaultRoutingSearchParameters()
    search_params_p1.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params_p1.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_params_p1.time_limit.seconds = 5
    
    solution_p1 = routing.SolveWithParameters(search_params_p1)
    
    if not solution_p1:
        return {'error': 'No solution found (constraints too tight?)'}
    
    # Count how many buses Phase 1 actually used
    buses_used_p1 = 0
    for v in range(num_vehicles):
        index = routing.Start(v)
        next_index = solution_p1.Value(routing.NextVar(index))
        if not routing.IsEnd(next_index):
            buses_used_p1 += 1
    
    print(f"Phase 1 result: {buses_used_p1} buses used (out of {num_vehicles})")
    
    # ===== PHASE 2: Refined solve with exact bus count (15 seconds) =====
    # Re-solve with exact bus count so solver focuses entirely on route quality
    
    # Identify WHICH vehicles were used in Phase 1 to preserve their specific capacities
    used_vehicle_indices = []
    for v in range(num_vehicles):
        index = routing.Start(v)
        if not routing.IsEnd(solution_p1.Value(routing.NextVar(index))):
            used_vehicle_indices.append(v)
    
    optimal_vehicles = len(used_vehicle_indices)
    
    # Build capacities for Phase 2 based on the ACTUAL vehicles used in Phase 1
    if vehicle_capacities:
        p2_capacities = [vehicle_capacities[i] for i in used_vehicle_indices]
        vehicle_map = used_vehicle_indices # Map Phase 2 vehicle_id -> Original vehicle_id
    else:
        p2_capacities = [40] * optimal_vehicles
        vehicle_map = list(range(optimal_vehicles)) # Fallback mapping (if homogeneous)

    print(f"--- Phase 2: Refined solve with {optimal_vehicles} vehicles (15s) ---")
    print(f"    Capacities: {p2_capacities}")
    
    manager, routing, capacities = _build_cvrp_model(
        school, students, optimal_vehicles, distance_matrix,
        max_ride_time_minutes, p2_capacities
    )
    
    search_params_p2 = pywrapcp.DefaultRoutingSearchParameters()
    search_params_p2.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params_p2.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_params_p2.time_limit.seconds = 15
    
    solution = routing.SolveWithParameters(search_params_p2)
    
    if not solution:
        # Fallback: Phase 2 failed, use Phase 1 result
        print("Phase 2 failed — falling back to Phase 1 solution")
        # Re-build with original count to extract Phase 1 solution
        manager, routing, capacities = _build_cvrp_model(
            school, students, num_vehicles, distance_matrix,
            max_ride_time_minutes, vehicle_capacities
        )
        search_params_p1.time_limit.seconds = 5
        solution = routing.SolveWithParameters(search_params_p1)
        optimal_vehicles = num_vehicles
        vehicle_map = list(range(num_vehicles)) # Reset map
        if not solution:
            return {'error': 'No solution found (constraints too tight?)'}
        
        # Reset map for Phase 1 fallback
        vehicle_map = list(range(num_vehicles))
    
    num_vehicles = optimal_vehicles  # Use for extraction below
    
    # ===== EXTRACT ROUTES (haversine-based, no API calls) =====
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
                student = students[next_node - 1]
                
                if node_index == 0:
                    distance_km = 0
                    time_s = 0
                else:
                    distance_m = distance_matrix[node_index][next_node]
                    distance_km = distance_m / 1000
                    time_s = estimate_travel_time(distance_km)
                
                route_distance += distance_km
                route_time += time_s + 60
                cumulative_time += time_s
                
                # Store data to process later (we need total route_time first)
                temp_route_data.append({
                    'student': student,
                    'relative_pickup_time': cumulative_time,
                    'segment_from': students[node_index - 1] if node_index > 0 else None,
                    'segment_to': student
                })
                
                cumulative_time += 60
                
                # Add segment: S(prev) -> S(curr)
                prev_student = students[node_index - 1] if node_index > 0 else None
                
                # OPEN VRP: Only add segment if there IS a previous student.
                # If prev_student is None (meaning node_index was 0/School), we do NOT add a segment.
                # This makes the route start visually at the first student.
                if prev_student:
                    route_segments.append({
                        'from': {'lat': prev_student['latitude'], 'lng': prev_student['longitude']},
                        'to': {'lat': student['latitude'], 'lng': student['longitude']},
                        'student': student['name']
                    })

            else:
                # Return to school
                from_point = students[node_index - 1] if node_index > 0 else school
                distance_m = distance_matrix[node_index][0]
                distance_km = distance_m / 1000
                time_s = estimate_travel_time(distance_km)
                
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
                    'student': student['name'],
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
            
            # Use haversine estimates (geometry fetched later in post-processing)
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
                                 school_arrival_time: int, max_ride_time_minutes: int) -> List[Dict]:
    """
    Post-processing: fetch real road geometry for all routes via OneMap API.
    Called ONCE after solve_cvrp returns, not inside the solving loop.
    Also recalculates pickup times and ride durations with real data.
    """
    print(f"\n=== Fetching road geometry for {len(routes)} route(s) ===")
    
    for route in routes:
        segments = route.get('segments', [])
        if not segments:
            continue
        
        enriched_segments = get_real_route_geometry_for_segments(segments, api_key)
        
        # Recalculate with real distances
        real_distance = sum(seg.get('distance', 0) for seg in enriched_segments)
        real_time = sum(seg.get('time', 0) for seg in enriched_segments) + (route['student_count'] * 60)
        
        actual_departure_time = school_arrival_time - int(real_time)
        
        # Recalculate student pickup times with real data
        cumulative_real_time = 0
        time_violations = []
        max_student_ride_time = 0
        
        for i, student_data in enumerate(route['students']):
            # Find the segment that leads TO this student
            # Segments are ordered: [School->S1, S1->S2, ..., Sn->School]
            # S1 is student index 0. Segment 0 leads to S1.
            # S2 is student index 1. Segment 1 leads to S2.
            
            if i < len(enriched_segments):
                cumulative_real_time += enriched_segments[i].get('time', 0)
            
            actual_pickup_time = actual_departure_time + cumulative_real_time
            ride_duration = school_arrival_time - actual_pickup_time
            cumulative_real_time += 60
            
            student_data['pickup_time'] = format_time(int(actual_pickup_time))
            student_data['ride_duration_minutes'] = round(ride_duration / 60, 1)
            max_student_ride_time = max(max_student_ride_time, ride_duration)
            
            if ride_duration > max_ride_time_minutes * 60:
                time_violations.append({
                    'student': student_data.get('name', 'Unknown'),
                    'ride_minutes': round(ride_duration / 60, 1),
                    'bus': route.get('bus_number', 0)
                })
        
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


def analyze_student_clusters(students: List[Dict], school: Dict) -> Dict:
    """
    Analyze student distribution to find hot spots and recommend bus allocation
    Uses DBSCAN for density-based clustering with proper distance metric
    """
    if len(students) < 2:
        # Return complete structure to avoid downstream KeyError
        return {
            'n_clusters': 1,
            'n_noise': 0,
            'cluster_info': [],
            'isolated_students': students if len(students) == 1 else [],
            'avg_cluster_distance': 0.0,
            'recommended_buses': 1,
            'min_buses': 1,
            'recommendation': 'Use 1 bus for few students',
            'visualization': {
                'clusters': [],
                'isolated': [
                    {'name': s['name'], 'lat': s['latitude'], 'lng': s['longitude'], 'address': s.get('address', '')}
                    for s in students
                ]
            }
        }
    
    # Extract coordinates
    coords = np.array([[s['latitude'], s['longitude']] for s in students])
    
    # Build distance matrix using haversine (in km)
    n = len(coords)
    distance_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            dist = haversine_distance(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
            distance_matrix[i][j] = dist
            distance_matrix[j][i] = dist
    
    # HYBRID CLUSTERING APPROACH
    # Step 1: Use smaller epsilon for tighter initial clusters
    # eps = 0.5 km (500m) - creates more specific neighborhood clusters
    # min_samples = 2 (at least 2 students nearby to start a cluster)
    clustering = DBSCAN(eps=1.5, min_samples=2, metric='precomputed').fit(distance_matrix)
    labels = np.array(clustering.labels_)
    
    # Count clusters (excluding noise points labeled as -1)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = list(labels).count(-1)
    
    print(f"\nCluster Analysis:")
    print(f"   Found {n_clusters} dense clusters")
    print(f"   {n_noise} isolated students")
    
    # Collect isolated students
    isolated_students = []
    if n_noise > 0:
        noise_mask = labels == -1
        isolated_students = [s for i, s in enumerate(students) if noise_mask[i]]
        print(f"   Isolated students: {[s['name'] for s in isolated_students]}")
    
    # Analyze each cluster
    cluster_info = []
    for cluster_id in set(labels):
        if cluster_id == -1:
            continue  # Skip noise
        
        cluster_mask = labels == cluster_id
        cluster_students = [s for i, s in enumerate(students) if cluster_mask[i]]
        cluster_coords = coords[cluster_mask]
        
        # Calculate cluster center
        center_lat = np.mean(cluster_coords[:, 0])
        center_lng = np.mean(cluster_coords[:, 1])
        
        # Calculate distance from school
        dist_from_school = haversine_distance(
            school['latitude'], school['longitude'],
            center_lat, center_lng
        )  # Already in km
        
        # Calculate cluster spread (max distance between any two points)
        max_spread = 0
        for i in range(len(cluster_coords)):
            for j in range(i + 1, len(cluster_coords)):
                dist = haversine_distance(
                    cluster_coords[i][0], cluster_coords[i][1],
                    cluster_coords[j][0], cluster_coords[j][1]
                )  # Already in km
                max_spread = max(max_spread, dist)
        
        cluster_info.append({
            'id': cluster_id,
            'size': len(cluster_students),
            'center': (center_lat, center_lng),
            'distance_from_school': dist_from_school,
            'spread': max_spread,
            'students': cluster_students
        })
        
        print(f"   Cluster {cluster_id + 1}: {len(cluster_students)} students, "
              f"{dist_from_school:.1f}km from school, spread: {max_spread:.1f}km")
    
    # ===== POST-PROCESSING: SPLIT AND MERGE CLUSTERS =====
    BUS_CAPACITY = 40
    MERGE_DISTANCE = 1.5  # km - merge clusters within 1.5km if combined fits in bus
    
    # Step 2: Split large clusters (> 40 students) using K-Means
    final_clusters = []
    for cluster in cluster_info:
        if cluster['size'] > BUS_CAPACITY:
            # Split this cluster into sub-clusters
            n_subclusters = math.ceil(cluster['size'] / BUS_CAPACITY)
            print(f"   Splitting large cluster ({cluster['size']} students) into {n_subclusters} sub-clusters")
            
            # Get coordinates for this cluster's students
            cluster_students = cluster['students']
            cluster_coords = np.array([[s['latitude'], s['longitude']] for s in cluster_students])
            
            # Use K-Means to split
            from sklearn.cluster import KMeans
            kmeans = KMeans(n_clusters=n_subclusters, random_state=42, n_init=10)
            sub_labels = kmeans.fit_predict(cluster_coords)
            
            # Create sub-clusters
            for sub_id in range(n_subclusters):
                sub_students = [s for i, s in enumerate(cluster_students) if sub_labels[i] == sub_id]
                if not sub_students:
                    continue
                sub_coords = np.array([[s['latitude'], s['longitude']] for s in sub_students])
                sub_center = (np.mean(sub_coords[:, 0]), np.mean(sub_coords[:, 1]))
                
                final_clusters.append({
                    'id': len(final_clusters),
                    'size': len(sub_students),
                    'center': sub_center,
                    'distance_from_school': haversine_distance(
                        school['latitude'], school['longitude'],
                        sub_center[0], sub_center[1]
                    ),
                    'spread': 0,  # Will recalculate if needed
                    'students': sub_students
                })
        else:
            cluster['id'] = len(final_clusters)
            final_clusters.append(cluster)
    
    # Step 3: Merge nearby small clusters if combined they fit in one bus
    merged = True
    while merged:
        merged = False
        i = 0
        while i < len(final_clusters):
            j = i + 1
            while j < len(final_clusters):
                c1, c2 = final_clusters[i], final_clusters[j]
                combined_size = c1['size'] + c2['size']
                
                # Check if close enough and combined fits in bus
                dist = haversine_distance(
                    c1['center'][0], c1['center'][1],
                    c2['center'][0], c2['center'][1]
                )
                
                if dist <= MERGE_DISTANCE and combined_size <= BUS_CAPACITY:
                    # Merge c2 into c1
                    merged_students = c1['students'] + c2['students']
                    merged_coords = np.array([[s['latitude'], s['longitude']] for s in merged_students])
                    merged_center = (np.mean(merged_coords[:, 0]), np.mean(merged_coords[:, 1]))
                    
                    c1['students'] = merged_students
                    c1['size'] = len(merged_students)
                    c1['center'] = merged_center
                    c1['distance_from_school'] = haversine_distance(
                        school['latitude'], school['longitude'],
                        merged_center[0], merged_center[1]
                    )
                    
                    final_clusters.pop(j)
                    merged = True
                    print(f"   Merged 2 nearby clusters into 1 ({combined_size} students)")
                else:
                    j += 1
            i += 1
    
    # Update cluster_info with final processed clusters
    cluster_info = final_clusters
    n_clusters = len(cluster_info)
    
    print(f"   Final: {n_clusters} clusters after split/merge")
    
    # Calculate distances between clusters
    cluster_distances = []
    for i in range(len(cluster_info)):
        for j in range(i + 1, len(cluster_info)):
            dist = haversine_distance(
                cluster_info[i]['center'][0], cluster_info[i]['center'][1],
                cluster_info[j]['center'][0], cluster_info[j]['center'][1]
            )  # Already in km
            cluster_distances.append(dist)
    
    # Recommend bus allocation
    # Always account for capacity (40 students per bus max)
    capacity_based_buses = max(1, math.ceil(len(students) / 40))
    
    # Check if isolated students are far from clusters
    isolated_far = False
    if isolated_students and cluster_info:
        for student in isolated_students:
            min_dist_to_cluster = float('inf')
            for cluster in cluster_info:
                dist = haversine_distance(
                    student['latitude'], student['longitude'],
                    cluster['center'][0], cluster['center'][1]
                )
                min_dist_to_cluster = min(min_dist_to_cluster, dist)
            if min_dist_to_cluster > 5:  # More than 5km from nearest cluster
                isolated_far = True
                break
    
    if n_clusters == 0:
        # No dense clusters, students are spread out
        buses_needed = capacity_based_buses
        recommendation = f"Students are spread out - use {buses_needed} bus(es)"
        min_buses = buses_needed
    elif n_clusters == 1:
        # One dense cluster - still respect capacity!
        buses_needed = capacity_based_buses
        if isolated_far:
            buses_needed = max(buses_needed, 2)  # At least 2 if isolated students are far
            recommendation = f"One cluster with far isolated students - use {buses_needed} bus(es)"
        else:
            recommendation = f"One dense cluster - use {buses_needed} bus(es)"
        min_buses = max(1, buses_needed - 1)  # Allow some flexibility
    else:
        # Multiple clusters - check if they're far apart
        avg_cluster_distance = np.mean(cluster_distances) if cluster_distances else 0
        
        if avg_cluster_distance > 5:
            # Far-apart clusters: recommend based on capacity, add a small buffer
            buses_needed = capacity_based_buses + min(n_clusters - 1, 5)  # Small buffer, not per-cluster
            if n_noise > 0:
                buses_needed += max(1, math.ceil(n_noise / 20))
            recommendation = f"Clusters are far apart ({avg_cluster_distance:.1f}km) - use {buses_needed} bus(es)"
            min_buses = capacity_based_buses
        else:
            buses_needed = capacity_based_buses
            recommendation = f"Clusters are close ({avg_cluster_distance:.1f}km) - use {buses_needed} bus(es)"
            min_buses = max(1, buses_needed - 1)
    
    print(f"   Recommendation: {recommendation}\n")
    
    return {
        'n_clusters': int(n_clusters),
        'n_noise': int(n_noise),
        'cluster_info': cluster_info,
        'isolated_students': isolated_students,
        'avg_cluster_distance': float(np.mean(cluster_distances)) if cluster_distances else 0.0,
        'recommended_buses': int(buses_needed),
        'min_buses': int(min_buses),  # Minimum buses to try
        'recommendation': recommendation,
        'visualization': {
            'clusters': [
                {
                    'id': int(c['id']),
                    'center': {'lat': float(c['center'][0]), 'lng': float(c['center'][1])},
                    # Use spread/2 as radius (spread is diameter), with minimum 500m for visibility
                    'radius': float(max(500, (c['spread'] / 2) * 1000)),  # Convert km to meters for Leaflet
                    'size': int(c['size']),
                    'distance_from_school': float(c['distance_from_school'])
                }
                for c in cluster_info
            ],
            'isolated': [
                {
                    'name': s['name'],
                    'lat': float(s['latitude']),
                    'lng': float(s['longitude']),
                    'address': s['address']
                }
                for s in isolated_students
            ]
        }
    }


def optimize_routes(school: Dict, students: List[Dict], max_buses: int, api_key: str, 
                    school_arrival_time: int = 27000, max_ride_time: int = 60,
                    fleet_capacities: List[int] = None) -> Dict:
    # FORCE RESET API HEALTH AND CACHE on every run to prevent stuck "straight line" state
    # This ensures if the user updates the API key, we immediately try again.
    global _api_healthy, distance_cache, route_geometry_cache
    _api_healthy = True
    distance_cache.clear()
    route_geometry_cache.clear()
    
    print(f"Optimize Routes: CACHE CLEARED. API Key Prefix: {api_key[:10]}... Len: {len(api_key)}")

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
    
    # ===== STEP 1: Analyze clusters for visualization and recommendation =====
    cluster_analysis = analyze_student_clusters(students, school)
    recommended_buses = cluster_analysis['recommended_buses']
    cluster_visualization = cluster_analysis.get('visualization', {})
    
    print(f"Cluster analysis recommends {recommended_buses} buses")
    print(f"   (This is just a suggestion - CVRP will optimize)\n")
    
    # ===== FLEET AWARE OPTIMIZATION =====
    if fleet_capacities and len(fleet_capacities) > 0:
        print(f"!!! USING HETEROGENEOUS FLEET !!!")
        print(f"Vehicles: {len(fleet_capacities)}, Capacities: {fleet_capacities}")

        # When using specific fleet, we skip the heuristic splitting and rely on the solver
        # to assign the right vehicle to the right set of students globally.

        result = solve_cvrp(school, students, len(fleet_capacities), api_key,
                           school_arrival_time=school_arrival_time,
                           max_ride_time_minutes=max_ride_time,
                           vehicle_capacities=fleet_capacities)

        # Add visualization info
        result['cluster_visualization'] = cluster_visualization

        # Handle infeasibility (hard time constraint too tight for available fleet)
        if 'error' in result or not result.get('routes'):
            # Estimate how many more buses might be needed
            total_capacity = sum(fleet_capacities)
            students_count = len(students)

            # Calculate a rough estimate of buses needed for time constraint
            estimated_buses_for_time = _estimate_buses_for_time_constraint(
                school, students, max_ride_time, fleet_capacities
            )

            error_msg = result.get('error', 'No feasible solution found')
            error_msg += '\n\n'
            error_msg += f'Fleet has {len(fleet_capacities)} vehicle(s) with total capacity {total_capacity}.\n'
            error_msg += f'With the {max_ride_time}-minute time constraint, '
            error_msg += f'you may need approximately {estimated_buses_for_time} vehicle(s).\n'
            error_msg += f'Current fleet: {len(fleet_capacities)} vehicle(s).\n'
            if estimated_buses_for_time > len(fleet_capacities):
                error_msg += f'>>> Please add at least {estimated_buses_for_time - len(fleet_capacities)} more vehicle(s) to your fleet.'

            return {
                'routes': [],
                'total_buses': 0,
                'error': error_msg,
                'cluster_visualization': cluster_visualization,
                'estimated_buses_needed': estimated_buses_for_time,
                'current_fleet_size': len(fleet_capacities)
            }

        # Enrich routes with real geometry
        enrich_routes_with_geometry(result['routes'], api_key, school_arrival_time, max_ride_time)

        # Check for time violations after geometry enrichment (real travel times)
        all_violations = []
        for route in result['routes']:
            if route.get('time_violations'):
                all_violations.extend(route['time_violations'])

        if all_violations:
            # Hard constraint should have prevented this, but check anyway after real geometry
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
            'cluster_visualization': cluster_visualization
        }
    
    # ===== CHECK: RECOMMENDED vs MAX BUSES (warn but don't block) =====
    if recommended_buses > max_buses:
        print(f"WARNING: Cluster analysis recommends {recommended_buses} buses but max is {max_buses}.")
        print(f"         Will attempt optimization with {max_buses} buses - may have time violations.")
    
    # ===== STEP 2: Decide routing strategy based on cluster separation =====
    avg_cluster_distance = cluster_analysis.get('avg_cluster_distance', 0)
    cluster_info = cluster_analysis.get('cluster_info', [])
    isolated_students = cluster_analysis.get('isolated_students', [])
    
    # Check if any isolated students are far (>7km) from clusters
    has_far_isolated = False
    for student in isolated_students:
        min_dist_to_cluster = float('inf')
        for cluster in cluster_info:
            if cluster and 'center' in cluster:
                dist = haversine_distance(
                    student['latitude'], student['longitude'],
                    cluster['center'][0], cluster['center'][1]
                )
                min_dist_to_cluster = min(min_dist_to_cluster, dist)
        if min_dist_to_cluster > 7:
            has_far_isolated = True
            print(f"  Far isolated student detected: {student['name']} is {min_dist_to_cluster:.1f}km from nearest cluster")
            break
    
    # Use split strategy if clusters are far apart OR there are far isolated students
    # BUT: Force UNIFIED if there are too many clusters (>10) to avoid exponential solve time
    too_many_clusters = len(cluster_info) > 10
    use_cluster_splitting = ((avg_cluster_distance > 5 and len(cluster_info) > 1) or has_far_isolated) and not too_many_clusters
    
    if too_many_clusters:
        print(f"NOTE: {len(cluster_info)} clusters detected - forcing UNIFIED strategy to avoid long solve times")
    
    if use_cluster_splitting:
        reason = "far isolated students" if has_far_isolated else f"clusters {avg_cluster_distance:.1f}km apart"
        print(f"Using SPLIT strategy ({reason})")
        return _solve_with_cluster_splitting(
            school, students, max_buses, api_key, 
            cluster_info, isolated_students, cluster_visualization, min_buses_needed,
            school_arrival_time, max_ride_time
        )
    else:
        print(f"Clusters are close ({avg_cluster_distance:.1f}km) - using UNIFIED strategy")
        return _solve_unified(
            school, students, max_buses, api_key, 
            cluster_visualization, min_buses_needed, school_arrival_time, max_ride_time
        )


def _solve_unified(school: Dict, students: List[Dict], max_buses: int, api_key: str,
                   cluster_visualization: Dict, min_buses_needed: int,
                   school_arrival_time: int = 27000, max_ride_time: int = 60) -> Dict:
    """
    Unified approach: all students go to single CVRP solver.
    Uses SetFixedCostOfVehicle to minimize buses in a single run.
    """
    print(f"Solving with up to {max_buses} bus(es)\n")

    result = solve_cvrp(school, students, max_buses, api_key,
                        school_arrival_time=school_arrival_time,
                        max_ride_time_minutes=max_ride_time)

    if 'error' in result or not result['routes']:
        # Estimate buses needed for time constraint
        estimated_buses = _estimate_buses_for_time_constraint(
            school, students, max_ride_time, [40] * max_buses
        )
        error_msg = result.get('error', 'No feasible solution found with hard time constraint')
        if estimated_buses > max_buses:
            error_msg += f'\n\nWith the {max_ride_time}-minute time constraint, '
            error_msg += f'you may need approximately {estimated_buses} bus(es). '
            error_msg += f'Current limit: {max_buses} bus(es).'

        return {
            'routes': [],
            'total_buses': 0,
            'error': error_msg,
            'cluster_visualization': cluster_visualization,
            'estimated_buses_needed': estimated_buses
        }

    # Enrich routes with real road geometry (post-processing)
    enrich_routes_with_geometry(result['routes'], api_key, school_arrival_time, max_ride_time)

    # Check for time violations after geometry enrichment (real travel times may differ)
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
            'cluster_visualization': cluster_visualization,
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
        'cluster_visualization': cluster_visualization,
        'routing_strategy': 'unified_optimized'
    }




def _solve_with_cluster_splitting(school: Dict, students: List[Dict], max_buses: int, api_key: str,
                                   cluster_info: List[Dict], isolated_students: List[Dict],
                                   cluster_visualization: Dict, min_buses_needed: int,
                                   school_arrival_time: int = 27000, max_ride_time: int = 60) -> Dict:
    """
    Split approach: solve CVRP independently for each cluster.
    Tracks a total bus budget to never exceed max_buses.
    """
    print(f"Solving {len(cluster_info)} clusters independently (budget: {max_buses} buses)...\n")
    
    cluster_students = _assign_isolated_to_clusters(cluster_info, isolated_students, school)
    
    all_routes = []
    total_distance = 0
    max_route_time = 0
    max_student_ride_time = 0
    bus_number = 1
    all_violations = []
    remaining_budget = max_buses  # Track how many buses are left
    
    for cluster_idx, (cluster, cluster_student_list) in enumerate(cluster_students):
        if not cluster_student_list:
            continue
        
        if remaining_budget <= 0:
            print(f"WARNING: No buses left for Cluster {cluster_idx + 1} ({len(cluster_student_list)} students) - skipping")
            continue
        
        cluster_min_buses = max(1, math.ceil(len(cluster_student_list) / 40))
        # Cap to remaining budget
        cluster_max_buses = min(cluster_min_buses + 1, remaining_budget)
        cluster_max_buses = max(cluster_min_buses, cluster_max_buses)
        
        print(f"=== Cluster {cluster_idx + 1}: {len(cluster_student_list)} students, budget: {remaining_budget} bus(es), trying {cluster_min_buses}-{cluster_max_buses} ===")
        
        best_cluster_result = None
        
        for num_buses in range(cluster_min_buses, cluster_max_buses + 1):
            try:
                result = solve_cvrp(school, cluster_student_list, num_buses, api_key,
                                   school_arrival_time=school_arrival_time,
                                   max_ride_time_minutes=max_ride_time)
                
                if 'error' in result:
                    print(f"  {num_buses} bus(es): FAILED - {result['error']}")
                elif not result.get('routes'):
                    print(f"  {num_buses} bus(es): FAILED - No routes")
                elif result.get('time_violations'):
                    print(f"  {num_buses} bus(es): {len(result['time_violations'])} violations")
                    if best_cluster_result is None:
                        best_cluster_result = result
                else:
                    print(f"  {num_buses} bus(es): Valid - {len(result['routes'])} route(s)")
                    if best_cluster_result is None or result['max_route_time'] < best_cluster_result['max_route_time']:
                        best_cluster_result = result
                    break
            except Exception as e:
                print(f"  {num_buses} bus(es): Exception - {e}")
        
        if best_cluster_result and best_cluster_result['routes']:
            buses_used = len(best_cluster_result['routes'])
            remaining_budget -= buses_used
            
            for route in best_cluster_result['routes']:
                route['bus_number'] = bus_number
                route['cluster_id'] = cluster_idx + 1
                all_routes.append(route)
                bus_number += 1
            
            total_distance += best_cluster_result['total_distance']
            max_route_time = max(max_route_time, best_cluster_result['max_route_time'])
            max_student_ride_time = max(max_student_ride_time, best_cluster_result.get('max_student_ride_time', 0))
            all_violations.extend(best_cluster_result.get('time_violations', []))
    
    if not all_routes:
        return {
            'routes': [],
            'total_buses': 0,
            'error': 'No valid routes found for any cluster.',
            'cluster_visualization': cluster_visualization
        }
    
    # Enrich routes with real road geometry (post-processing)
    enrich_routes_with_geometry(all_routes, api_key, school_arrival_time, max_ride_time)
    
    selection_note = f"Split routing: {len(all_routes)} bus(es) across {len(cluster_students)} groups"
    print(f"\nResult: {selection_note}")
    
    return {
        'routes': all_routes,
        'total_buses': len(all_routes),
        'max_route_time_minutes': round(max_route_time / 60, 1),
        'max_student_ride_time_minutes': round(max_student_ride_time / 60, 1),
        'total_distance_km': round(total_distance, 2),
        'optimization_note': selection_note,
        'cluster_visualization': cluster_visualization,
        'routing_strategy': 'split_by_cluster'
    }


def _assign_isolated_to_clusters(cluster_info: List[Dict], isolated_students: List[Dict], 
                                  school: Dict) -> List[Tuple[Dict, List[Dict]]]:
    """
    Assign isolated students to clusters ONLY if they are within 7km.
    Students farther than 7km from all clusters get their own separate group.
    Returns list of (cluster, students) tuples.
    """
    MAX_MERGE_DISTANCE = 7  # km - don't merge if farther than this
    
    # Start with cluster students
    cluster_students = [(c, list(c['students'])) for c in cluster_info]
    
    # Separate far isolated students
    far_isolated = []
    near_isolated = []
    
    for student in isolated_students:
        min_dist = float('inf')
        nearest_idx = 0
        
        for idx, (cluster, _) in enumerate(cluster_students):
            if cluster and 'center' in cluster:
                dist = haversine_distance(
                    student['latitude'], student['longitude'],
                    cluster['center'][0], cluster['center'][1]
                )
                if dist < min_dist:
                    min_dist = dist
                    nearest_idx = idx
        
        if min_dist <= MAX_MERGE_DISTANCE:
            # Close enough - merge with cluster
            near_isolated.append((student, nearest_idx, min_dist))
        else:
            # Too far - keep separate
            far_isolated.append(student)
            print(f"  FAR: '{student['name']}' is {min_dist:.1f}km from nearest cluster - separate bus")
    
    # Merge near isolated students into their clusters
    for student, idx, dist in near_isolated:
        if cluster_students:
            cluster_students[idx][1].append(student)
            print(f"  Merged '{student['name']}' to Cluster {idx + 1} ({dist:.1f}km)")
    
    # If no clusters exist, create one group from near isolated
    if not cluster_students:
        cluster_students = [({}, near_isolated if near_isolated else [])]
    
    # Add far isolated students as their own separate group(s)
    # Group them by proximity to each other (within 3km)
    if far_isolated:
        far_groups = _group_far_isolated(far_isolated)
        for group in far_groups:
            # Create a pseudo-cluster for each group
            cluster_students.append(({'id': 'isolated', 'students': group}, group))
            print(f"  Created separate group with {len(group)} far isolated student(s)")
    
    return cluster_students


def _group_far_isolated(far_isolated: List[Dict]) -> List[List[Dict]]:
    """
    Group far isolated students that are within 3km of each other.
    Returns list of student groups.
    """
    if len(far_isolated) <= 1:
        return [far_isolated] if far_isolated else []
    
    groups = []
    used = set()
    
    for i, student in enumerate(far_isolated):
        if i in used:
            continue
        
        group = [student]
        used.add(i)
        
        # Find nearby students
        for j, other in enumerate(far_isolated):
            if j in used:
                continue
            dist = haversine_distance(
                student['latitude'], student['longitude'],
                other['latitude'], other['longitude']
            )
            if dist <= 3:  # Within 3km of each other
                group.append(other)
                used.add(j)
        
        groups.append(group)

    return groups


def _select_best_solution(results: List[Dict], all_results_with_violations: List[Dict],
                          max_buses: int, cluster_visualization: Dict) -> Dict:
    """
    Select the best solution from results, preferring comfortable ride times.
    """
    if not results:
        if all_results_with_violations:
            min_violations = min(len(r['time_violations']) for r in all_results_with_violations)
            error_msg = f'No valid routes found. All {len(all_results_with_violations)} configuration(s) had time violations. '
            error_msg += f'Best attempt had {min_violations} violation(s). Consider increasing max_buses beyond {max_buses}.'
        else:
            error_msg = 'No routes could be generated. CVRP solver failed for all bus counts. '
            error_msg += 'Possible causes: constraints too tight, students too spread out, or unreachable locations.'
        
        return {
            'routes': [],
            'total_buses': 0,
            'error': error_msg,
            'cluster_visualization': cluster_visualization
        }
    
    comfortable_threshold = 45 * 60  # 45 minutes
    comfortable = [r for r in results if r['max_student_ride_time'] < comfortable_threshold]
    
    if comfortable:
        best = min(comfortable, key=lambda x: (x['num_buses'], x['max_student_ride_time']))
        selection_note = f"Selected {best['num_buses']} bus(es) - comfortable ride times (<45 min)"
    else:
        best = min(results, key=lambda x: (x['max_student_ride_time'], x['num_buses']))
        selection_note = f"Selected {best['num_buses']} bus(es) - shortest ride time available"
    
    print(f"\nResult: {selection_note}")
    
    return {
        'routes': best['routes'],
        'total_buses': best['num_buses'],
        'max_route_time_minutes': round(best['max_time'] / 60, 1),
        'max_student_ride_time_minutes': round(best['max_student_ride_time'] / 60, 1),
        'total_distance_km': round(best['total_distance'], 2),
        'optimization_note': selection_note,
        'cluster_visualization': cluster_visualization,
        'routing_strategy': 'unified'
    }


def _estimate_buses_for_time_constraint(school: Dict, students: List[Dict],
                                        max_ride_time_minutes: int,
                                        fleet_capacities: List[int]) -> int:
    """
    Estimate how many buses are needed to meet the time constraint.
    This is a heuristic based on student distribution and distance from school.

    Logic:
    1. Calculate average distance from school
    2. Estimate route time per student (travel + pickup)
    3. Calculate how many students can fit in one route within time limit
    4. Estimate total buses needed
    """
    if not students:
        return 1

    max_ride_seconds = max_ride_time_minutes * 60

    # Calculate distances from school for all students
    distances_from_school = []
    for student in students:
        dist = haversine_distance(
            school['latitude'], school['longitude'],
            student['latitude'], student['longitude']
        )
        distances_from_school.append(dist)

    avg_distance = sum(distances_from_school) / len(distances_from_school)
    max_distance = max(distances_from_school)

    # Estimate time components
    # Average speed: 50 km/h = ~8.3 min per km
    # Road factor: ~1.5x for urban driving
    travel_time_per_km = (1 / 50) * 60 * 1.5  # minutes per km (with road factor)
    pickup_time_per_student = 1  # minute per student

    # Estimate average route time for a student at avg distance
    # This includes: travel to student + pickup + travel to next student + ... + travel to school
    # Simplified: assume each student adds avg travel segment + pickup
    avg_time_per_student = (avg_distance * travel_time_per_km / 2) + pickup_time_per_student

    # Add base time (first pickup and return to school)
    base_route_time = max_distance * travel_time_per_km  # Time to reach farthest + return

    # How many students can fit in one route?
    available_time_for_pickups = max_ride_seconds / 60 - base_route_time
    if available_time_for_pickups <= 0:
        # Even one student might exceed time limit (school is very far)
        students_per_route = 1
    else:
        students_per_route = max(1, int(available_time_for_pickups / avg_time_per_student))

    # Capacity constraint
    avg_capacity = sum(fleet_capacities) / len(fleet_capacities) if fleet_capacities else 40
    students_per_route = min(students_per_route, int(avg_capacity))

    # Calculate buses needed
    buses_for_time = math.ceil(len(students) / students_per_route)

    # Minimum buses for capacity
    total_capacity = sum(fleet_capacities) if fleet_capacities else 40 * buses_for_time
    buses_for_capacity = math.ceil(len(students) / (total_capacity / len(fleet_capacities)))

    # Take the higher of the two
    estimated_buses = max(buses_for_time, buses_for_capacity)

    # Add a safety margin (20% more buses)
    estimated_buses = math.ceil(estimated_buses * 1.2)

    print(f"  Estimation: avg_dist={avg_distance:.1f}km, max_dist={max_distance:.1f}km")
    print(f"  Estimation: students_per_route={students_per_route}, buses_for_time={buses_for_time}")
    print(f"  Estimation: total estimated buses (with margin)={estimated_buses}")

    return max(estimated_buses, len(fleet_capacities) if fleet_capacities else 1)


# Remove old clustering function - OR-Tools handles this automatically
