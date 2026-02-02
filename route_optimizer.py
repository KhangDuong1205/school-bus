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
cache_school_hash = None  # Track school location for cache invalidation

# Rate limiting for API calls - Lock initialized at module level to avoid race condition
rate_limit_lock = Lock()
cache_lock = Lock()  # For thread-safe cache file access
last_api_call_time = 0
MIN_API_INTERVAL = 0.2  # 200ms between calls = max 5/sec


def load_cache_from_file():
    """Load cache from JSON file on startup"""
    global distance_cache, route_geometry_cache
    
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                distance_cache = data.get('distance_cache', {})
                route_geometry_cache = data.get('route_geometry_cache', {})
                print(f"Loaded cache: {len(distance_cache)} distance entries, {len(route_geometry_cache)} geometry entries")
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
                'route_geometry_cache': route_geometry_cache
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
        'total_cached_items': len(distance_cache) + len(route_geometry_cache),
        'cache_file': CACHE_FILE,
        'cache_file_exists': os.path.exists(CACHE_FILE)
    }


def clear_cache():
    """Clear all caches"""
    global distance_cache, route_geometry_cache, cache_school_hash
    distance_cache.clear()
    route_geometry_cache.clear()
    cache_school_hash = None
    save_cache_to_file()  # Also clear the file
    print("Cache cleared")


def invalidate_cache_if_school_changed(school: Dict):
    """Invalidate cache if school location has changed"""
    global cache_school_hash, distance_cache, route_geometry_cache
    
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
    Includes caching, retry logic, and rate limiting
    """
    global last_api_call_time
    
    # Create cache key (round to 4 decimal places for ~11m precision)
    cache_key = f"{start_lat:.4f},{start_lng:.4f}->{end_lat:.4f},{end_lng:.4f}"
    
    # Check cache first
    if cache_key in distance_cache:
        print(f"  Cache hit: {cache_key}")
        return distance_cache[cache_key]
    
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
                    
                    # Cache the result and persist to file
                    distance_cache[cache_key] = result
                    save_cache_to_file()  # Persist to disk
                    print(f"  API success + cached: {cache_key}")
                    
                    return result
            
            # If we get here, API returned non-200 or invalid data
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
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
            # Short distances (<2km): 1.5x (dense urban, many turns)
            # Medium distances (2-10km): 1.35x (suburban)
            # Long distances (>10km): 1.25x (highways)
            if distance_km < 2:
                road_factor = 1.5
            elif distance_km < 10:
                road_factor = 1.35
            else:
                road_factor = 1.25
            
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
        from_lat = segment['from']['lat']
        from_lng = segment['from']['lng']
        to_lat = segment['to']['lat']
        to_lng = segment['to']['lng']
        
        # Get real route from OneMap
        distance_km, time_s, geometry = get_route_from_onemap(
            from_lat, from_lng, to_lat, to_lng, api_key
        )
        
        # Update segment with real data
        segment['geometry'] = geometry
        segment['distance'] = distance_km
        segment['time'] = time_s
        
        return segment
    
    # Parallel API calls (max 5 concurrent to avoid rate limits)
    enriched_segments = [None] * len(route_segments)
    with ThreadPoolExecutor(max_workers=5) as executor:
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
                distance_matrix[j][i] = distance_m
            except Exception as e:
                pair = futures[future]
                i, j = pair
                # Fallback to haversine
                distance_km = haversine_distance(
                    points[i]['latitude'], points[i]['longitude'],
                    points[j]['latitude'], points[j]['longitude']
                )
                distance_m = int(distance_km * 1.35 * 1000)  # Apply road factor
                distance_matrix[i][j] = distance_m
                distance_matrix[j][i] = distance_m
                print(f"  Pair ({i},{j}) fallback: {e}")
    
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


def solve_cvrp(school: Dict, students: List[Dict], num_vehicles: int, api_key: str, 
               max_route_time_minutes: int = 60,
               school_arrival_time: int = 27000,  # 7:30 AM in seconds from midnight
               max_ride_time_minutes: int = 60) -> Dict:
    """
    Solve Capacitated Vehicle Routing Problem using Google OR-Tools
    Uses haversine for optimization, OneMap for final display
    
    Args:
        max_route_time_minutes: Maximum allowed route time in minutes (default 60)
        school_arrival_time: Target arrival time at school in seconds from midnight (default 7:30 AM)
        max_ride_time_minutes: Maximum time any student should be on bus (default 60)
    """
    if not students:
        return {'routes': [], 'total_distance': 0, 'total_time': 0}
    
    # Build distance matrix FAST using haversine
    distance_matrix = build_distance_matrix_fast(school, students)
    points = [school] + students
    
    # Create routing model
    manager = pywrapcp.RoutingIndexManager(
        len(distance_matrix),  # Number of locations
        num_vehicles,          # Number of vehicles
        0                      # Depot (school) index
    )
    
    routing = pywrapcp.RoutingModel(manager)
    
    # Create distance callback
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]
    
    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    
    # Add capacity constraint (40 students per bus)
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return 1 if from_node > 0 else 0  # Each student = 1, school = 0
    
    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        [40] * num_vehicles,  # vehicle maximum capacities
        True,  # start cumul to zero
        'Capacity'
    )
    
    # Add time constraint with staggered departures
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        
        # Distance in meters
        distance_m = distance_matrix[from_node][to_node]
        distance_km = distance_m / 1000
        
        # Travel time + pickup time (60s per student)
        travel_time = estimate_travel_time(distance_km)
        pickup_time = 60 if to_node > 0 else 0  # 60s pickup, 0s at school
        
        return int(travel_time + pickup_time)
    
    time_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.AddDimension(
        time_callback_index,
        slack_max=1800,  # 30 min slack (waiting time allowed)
        capacity=10800,  # 3 hours max total route time (allows early departure for distant students)
        fix_start_cumul_to_zero=False,  # CRITICAL: Allow staggered departures
        name='Time'
    )
    
    time_dimension = routing.GetDimensionOrDie('Time')
    
    # Calculate time windows
    max_ride_seconds = int(max_ride_time_minutes * 60)
    
    # Each student's ride time = school_arrival - pickup_time
    # For ride time to be <= max_ride_seconds, pickup must be >= (school_arrival - max_ride_seconds)
    earliest_pickup = school_arrival_time - max_ride_seconds
    
    try:
        # Set per-student constraints: each student must be picked up within max_ride_time of school arrival
        for node_index in range(1, len(students) + 1):  # Skip depot (index 0)
            index = manager.NodeToIndex(node_index)
            # Student must be picked up no earlier than (school_arrival - max_ride_time)
            # This ensures their ride time is <= max_ride_time
            time_dimension.CumulVar(index).SetRange(
                earliest_pickup,        # Cannot be picked up too early (would ride too long)
                school_arrival_time     # Cannot be picked up after school start
            )
        
        # Set vehicle end constraints (arrival at school)
        for vehicle_id in range(num_vehicles):
            end_index = routing.End(vehicle_id)
            # Must arrive at school on time
            time_dimension.CumulVar(end_index).SetRange(
                earliest_pickup,         # Earliest arrival
                school_arrival_time      # Latest arrival (school start time)
            )
    except Exception as e:
        return {'error': f'Time constraints infeasible: {e}. Try adding more buses or increasing max ride time.'}
    
    # Add fixed cost per vehicle to minimize number of buses used
    # Lowered to allow extra buses when routes would be too long
    VEHICLE_FIXED_COST = 20000  # Balanced cost - allows extra buses for better routes
    for vehicle_id in range(num_vehicles):
        routing.SetFixedCostOfVehicle(VEHICLE_FIXED_COST, vehicle_id)
    
    # OBJECTIVE: Minimize the maximum route time (span)
    # This ensures we balance routes rather than having one very long route
    time_dimension.SetGlobalSpanCostCoefficient(100)  # Penalize difference between longest and shortest
    
    # Set search parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    # Increased time limit since we now solve once with vehicle minimization
    search_parameters.time_limit.seconds = 30
    
    print(f"Solving CVRP with {num_vehicles} vehicles, max {max_route_time_minutes} min per route...")
    solution = routing.SolveWithParameters(search_parameters)
    
    if not solution:
        return {'error': 'No solution found (constraints too tight?)'}
    
    # Extract routes with time validation
    routes = []
    total_distance = 0
    max_route_time = 0
    max_student_ride_time = 0
    time_violations = []
    
    time_dimension = routing.GetDimensionOrDie('Time')
    
    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        
        # Get departure time from solution
        departure_time = solution.Min(time_dimension.CumulVar(index))
        
        route_distance = 0
        route_time = 0
        route_students = []
        route_segments = []
        cumulative_time = 0
        
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            next_index = solution.Value(routing.NextVar(index))
            next_node = manager.IndexToNode(next_index)
            
            if node_index == 0 and next_node == 0:
                # Empty route
                break
            
            if next_node != 0:  # Not returning to depot yet
                # Add student
                student = students[next_node - 1]
                
                # Calculate distance from matrix (haversine-based)
                distance_m = distance_matrix[node_index][next_node]
                distance_km = distance_m / 1000
                time_s = estimate_travel_time(distance_km)
                
                route_distance += distance_km
                route_time += time_s + 60  # +60s pickup time
                
                # Update cumulative time FIRST (travel to this student)
                cumulative_time += time_s
                
                # Calculate this student's pickup time and ride duration
                pickup_time = departure_time + cumulative_time
                ride_duration = school_arrival_time - pickup_time
                
                # Add pickup time to cumulative (student boarding)
                cumulative_time += 60
                
                # Track max ride time and violations
                max_student_ride_time = max(max_student_ride_time, ride_duration)
                if ride_duration > max_ride_time_minutes * 60:
                    time_violations.append({
                        'student': student['name'],
                        'ride_minutes': round(ride_duration / 60, 1),
                        'bus': vehicle_id + 1
                    })
                
                # Add student with time info
                route_students.append({
                    **student,
                    'pickup_time': format_time(int(pickup_time)),
                    'ride_duration_minutes': round(ride_duration / 60, 1)
                })
                
                # Add segment (without real geometry yet)
                from_point = school if node_index == 0 else students[node_index - 1]
                route_segments.append({
                    'from': {'lat': from_point['latitude'], 'lng': from_point['longitude']},
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
        
        if route_students:  # Only add non-empty routes
            # NOW get real road geometry for this route
            print(f"  Bus {vehicle_id + 1}: {len(route_students)} students")
            enriched_segments = get_real_route_geometry_for_segments(route_segments, api_key)
            
            # Recalculate with real distances
            real_distance = sum(seg['distance'] for seg in enriched_segments)
            real_time = sum(seg['time'] for seg in enriched_segments) + (len(route_students) * 60)
            
            # Recalculate actual departure time based on real route time
            actual_departure_time = school_arrival_time - int(real_time)
            
            # CRITICAL: Recalculate all student pickup times with real data
            cumulative_real_time = 0
            for i, student_data in enumerate(route_students):
                # Add travel time from prev (or school) to this student FIRST
                if i < len(enriched_segments):
                    cumulative_real_time += enriched_segments[i]['time']
                
                actual_pickup_time = actual_departure_time + cumulative_real_time
                ride_duration = school_arrival_time - actual_pickup_time
                
                # Add pickup duration (60s) for next leg
                cumulative_real_time += 60
                
                # Update student with corrected times
                student_data['pickup_time'] = format_time(int(actual_pickup_time))
                student_data['ride_duration_minutes'] = round(ride_duration / 60, 1)
                
                # Check for violations with real times
                if ride_duration > max_ride_time_minutes * 60:
                    # Update violations list
                    violation_found = False
                    for v in time_violations:
                        if v['student'] == student_data['name'] and v['bus'] == vehicle_id + 1:
                            v['ride_minutes'] = round(ride_duration / 60, 1)
                            violation_found = True
                            break
                    if not violation_found:
                        time_violations.append({
                            'student': student_data['name'],
                            'ride_minutes': round(ride_duration / 60, 1),
                            'bus': vehicle_id + 1
                        })
                
                # ALWAYS update max_student_ride_time with real data
                max_student_ride_time = max(max_student_ride_time, ride_duration)
            
            routes.append({
                'students': route_students,
                'distance_km': round(real_distance, 2),
                'time_seconds': round(real_time),
                'time_minutes': round(real_time / 60, 1),
                'student_count': len(route_students),
                'segments': enriched_segments,
                'departure_time': format_time(actual_departure_time),
                'arrival_time': format_time(school_arrival_time)
            })
            
            total_distance += real_distance
            max_route_time = max(max_route_time, real_time)
    
    # Report time violations
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
    
    # DBSCAN clustering with precomputed distances
    # eps = 1.5 km radius (tighter clusters to separate nearby areas)
    # min_samples = 3 (at least 3 students to form a cluster)
    clustering = DBSCAN(eps=1.5, min_samples=3, metric='precomputed').fit(distance_matrix)
    labels = clustering.labels_
    
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
        
        if avg_cluster_distance > 5:  # Lowered from 7km to 5km
            # Each cluster should get its own bus(es)
            buses_needed = sum(max(1, math.ceil(c['size'] / 40)) for c in cluster_info)
            # Add buses for isolated students
            if n_noise > 0:
                buses_needed += max(1, math.ceil(n_noise / 10))  # More buses for isolated
            recommendation = f"Clusters are far apart ({avg_cluster_distance:.1f}km) - use {buses_needed} bus(es)"
            min_buses = buses_needed
        else:
            # Clusters are close - can share buses
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
                    school_arrival_time: int = 27000, max_ride_time: int = 60) -> Dict:
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
    use_cluster_splitting = (avg_cluster_distance > 5 and len(cluster_info) > 1) or has_far_isolated
    
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
    
    # First attempt: solve with max_buses, let OR-Tools minimize
    result = solve_cvrp(school, students, max_buses, api_key, 
                        school_arrival_time=school_arrival_time,
                        max_ride_time_minutes=max_ride_time)
    
    if 'error' in result or not result['routes']:
        return {
            'routes': [],
            'total_buses': 0,
            'error': result.get('error', 'CVRP solver failed to find a solution'),
            'cluster_visualization': cluster_visualization
        }
    
    # Check for time violations
    if not result.get('time_violations'):
        # Success! No violations
        selection_note = f"Optimal: {result['num_buses']} bus(es) with vehicle minimization"
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
    
    # If we have violations, the routes are too long - try with more focus on time
    # Return the result anyway but mark as having violations
    print(f"Solution has {len(result['time_violations'])} time violation(s)")
    
    return {
        'routes': result['routes'],
        'total_buses': result['num_buses'],
        'max_route_time_minutes': round(result['max_route_time'] / 60, 1),
        'max_student_ride_time_minutes': round(result.get('max_student_ride_time', 0) / 60, 1),
        'total_distance_km': round(result['total_distance'], 2),
        'optimization_note': f"Warning: {len(result['time_violations'])} student(s) exceed ride time limit",
        'time_violations': result['time_violations'],
        'cluster_visualization': cluster_visualization,
        'routing_strategy': 'unified_with_violations'
    }




def _solve_with_cluster_splitting(school: Dict, students: List[Dict], max_buses: int, api_key: str,
                                   cluster_info: List[Dict], isolated_students: List[Dict],
                                   cluster_visualization: Dict, min_buses_needed: int,
                                   school_arrival_time: int = 27000, max_ride_time: int = 60) -> Dict:
    """
    Split approach: solve CVRP independently for each cluster.
    Used when clusters are far apart (>7km).
    """
    print(f"Solving {len(cluster_info)} clusters independently...\n")
    
    # Assign isolated students to nearest cluster
    cluster_students = _assign_isolated_to_clusters(cluster_info, isolated_students, school)
    
    all_routes = []
    total_distance = 0
    max_route_time = 0
    max_student_ride_time = 0
    bus_number = 1
    all_violations = []
    
    for cluster_idx, (cluster, cluster_student_list) in enumerate(cluster_students):
        if not cluster_student_list:
            continue
            
        # Calculate buses needed for this cluster
        cluster_min_buses = max(1, math.ceil(len(cluster_student_list) / 40))
        cluster_max_buses = min(cluster_min_buses + 2, max_buses - (len(cluster_info) - 1))  # Reserve buses for other clusters
        cluster_max_buses = max(cluster_min_buses, cluster_max_buses)
        
        print(f"=== Cluster {cluster_idx + 1}: {len(cluster_student_list)} students, trying {cluster_min_buses}-{cluster_max_buses} bus(es) ===")
        
        best_cluster_result = None
        
        for num_buses in range(cluster_min_buses, cluster_max_buses + 1):
            try:
                result = solve_cvrp(school, cluster_student_list, num_buses, api_key,
                                   school_arrival_time=school_arrival_time,
                                   max_ride_time_minutes=max_ride_time)
                
                # Debug logging
                if 'error' in result:
                    print(f"  {num_buses} bus(es): FAILED - {result['error']}")
                elif not result.get('routes'):
                    print(f"  {num_buses} bus(es): FAILED - No routes returned")
                elif result.get('time_violations'):
                    print(f"  {num_buses} bus(es): {len(result['time_violations'])} violations")
                    if best_cluster_result is None:
                        best_cluster_result = result  # Keep as fallback
                else:
                    print(f"  {num_buses} bus(es): Valid - {len(result['routes'])} route(s)")
                    if best_cluster_result is None or result['max_route_time'] < best_cluster_result['max_route_time']:
                        best_cluster_result = result
                    break  # Take first valid solution for this cluster
            except Exception as e:
                print(f"  {num_buses} bus(es): Exception - {e}")
        
        if best_cluster_result and best_cluster_result['routes']:
            # Renumber buses and add to combined results
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
    
    selection_note = f"Split routing: {len(all_routes)} bus(es) across {len(cluster_info)} clusters"
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


# Remove old clustering function - OR-Tools handles this automatically
