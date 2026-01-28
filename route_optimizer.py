"""
Route optimization algorithm for school bus routing
Uses Google OR-Tools CVRP solver with real driving distances
Includes smart density-based pre-clustering for bus allocation
"""
import math
from typing import List, Dict, Tuple
import requests
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import numpy as np
from sklearn.cluster import DBSCAN


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
    Assumes average speed of 30 km/h in residential areas
    """
    avg_speed_kmh = 30
    time_hours = distance_km / avg_speed_kmh
    return time_hours * 3600  # convert to seconds


def get_route_from_onemap(start_lat: float, start_lng: float, end_lat: float, end_lng: float, api_key: str) -> Tuple[float, float, List]:
    """Get actual route distance, time, and geometry from OneMap routing API"""
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
                
                return distance_m / 1000, time_s, geometry
    except Exception as e:
        print(f"OneMap API error: {e}")
    
    # Fallback to haversine estimation with straight line
    distance = haversine_distance(start_lat, start_lng, end_lat, end_lng)
    time = estimate_travel_time(distance)
    geometry = [[start_lat, start_lng], [end_lat, end_lng]]
    return distance, time, geometry


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
    Build distance matrix using haversine (straight-line) distances
    FAST: No API calls, instant calculation
    Returns: distance_matrix in meters
    """
    points = [school] + students
    n = len(points)
    distance_matrix = [[0] * n for _ in range(n)]
    
    print(f"⚡ Building fast distance matrix for {n} points using haversine...")
    
    for i in range(n):
        for j in range(i + 1, n):
            # Calculate straight-line distance in km
            distance_km = haversine_distance(
                points[i]['latitude'], points[i]['longitude'],
                points[j]['latitude'], points[j]['longitude']
            )
            
            # Apply road factor (roads are typically 1.3x longer than straight line)
            # Convert to meters for OR-Tools
            distance_m = int(distance_km * 1.3 * 1000)
            
            distance_matrix[i][j] = distance_m
            distance_matrix[j][i] = distance_m
    
    print("✅ Fast distance matrix built!")
    return distance_matrix


def get_real_route_geometry_for_segments(route_segments: List[Dict], api_key: str) -> List[Dict]:
    """
    Get real road geometry from OneMap for route segments
    Called AFTER optimization to display real roads on map
    """
    print(f"🗺️  Fetching real road geometry for {len(route_segments)} segments...")
    
    enriched_segments = []
    
    for segment in route_segments:
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
        
        enriched_segments.append(segment)
    
    print("✅ Real road geometry fetched!")
    return enriched_segments


def solve_cvrp(school: Dict, students: List[Dict], num_vehicles: int, api_key: str) -> Dict:
    """
    Solve Capacitated Vehicle Routing Problem using Google OR-Tools
    Uses haversine for optimization, OneMap for final display
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
    
    # Set search parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 30
    
    print("Solving CVRP...")
    solution = routing.SolveWithParameters(search_parameters)
    
    if not solution:
        return {'error': 'No solution found'}
    
    # Extract routes (without real geometry yet)
    routes = []
    total_distance = 0
    max_route_time = 0
    
    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        route_distance = 0
        route_time = 0
        route_students = []
        route_segments = []
        
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
                route_students.append(student)
                
                # Calculate distance from matrix (haversine-based)
                distance_m = distance_matrix[node_index][next_node]
                distance_km = distance_m / 1000
                time_s = estimate_travel_time(distance_km)
                
                route_distance += distance_km
                route_time += time_s + 60  # +60s pickup time
                
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
                
                route_segments.append({
                    'from': {'lat': from_point['latitude'], 'lng': from_point['longitude']},
                    'to': {'lat': school['latitude'], 'lng': school['longitude']},
                    'student': 'Return to School'
                })
            
            index = next_index
        
        if route_students:  # Only add non-empty routes
            # NOW get real road geometry for this route
            print(f"  📍 Bus {vehicle_id + 1}: {len(route_students)} students, fetching real roads...")
            enriched_segments = get_real_route_geometry_for_segments(route_segments, api_key)
            
            # Recalculate with real distances
            real_distance = sum(seg['distance'] for seg in enriched_segments)
            real_time = sum(seg['time'] for seg in enriched_segments) + (len(route_students) * 60)
            
            routes.append({
                'students': route_students,
                'distance_km': round(real_distance, 2),
                'time_seconds': round(real_time),
                'time_minutes': round(real_time / 60, 1),
                'student_count': len(route_students),
                'segments': enriched_segments
            })
            
            total_distance += real_distance
            max_route_time = max(max_route_time, real_time)
    
    print(f"CVRP solved! {len(routes)} routes, Total distance: {total_distance:.2f} km")
    
    return {
        'routes': routes,
        'total_distance': total_distance,
        'max_route_time': max_route_time,
        'num_buses': len(routes)
    }


def analyze_student_clusters(students: List[Dict], school: Dict) -> Dict:
    """
    Analyze student distribution to find hot spots and recommend bus allocation
    Uses DBSCAN for density-based clustering
    """
    if len(students) < 2:
        return {'clusters': 1, 'recommendation': 'Use 1 bus for few students'}
    
    # Extract coordinates
    coords = np.array([[s['latitude'], s['longitude']] for s in students])
    
    # DBSCAN clustering
    # eps = 0.03 degrees ≈ 3km radius (increased to capture more students per cluster)
    # min_samples = 3 (at least 3 students to form a cluster)
    clustering = DBSCAN(eps=0.03, min_samples=3).fit(coords)
    labels = clustering.labels_
    
    # Count clusters (excluding noise points labeled as -1)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = list(labels).count(-1)
    
    print(f"\n🔍 Cluster Analysis:")
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
    if n_clusters == 0:
        # No dense clusters, students are spread out
        buses_needed = max(1, math.ceil(len(students) / 40))
        recommendation = f"Students are spread out - use {buses_needed} bus(es)"
        min_buses = buses_needed
    elif n_clusters == 1:
        # One dense cluster
        buses_needed = max(1, math.ceil(len(students) / 40))
        recommendation = f"One dense cluster - use {buses_needed} bus(es)"
        min_buses = 1
    else:
        # Multiple clusters - check if they're far apart
        avg_cluster_distance = np.mean(cluster_distances) if cluster_distances else 0
        
        if avg_cluster_distance > 7:  # Clusters are >7km apart
            # Each cluster should get its own bus(es)
            buses_needed = sum(max(1, math.ceil(c['size'] / 40)) for c in cluster_info)
            # Add buses for isolated students
            if n_noise > 0:
                buses_needed += math.ceil(n_noise / 40)
            recommendation = f"Clusters are far apart ({avg_cluster_distance:.1f}km) - use {buses_needed} bus(es), one per cluster"
            min_buses = buses_needed  # Don't try fewer buses
        else:
            # Clusters are close - can share buses
            buses_needed = max(1, math.ceil(len(students) / 40))
            recommendation = f"Clusters are close ({avg_cluster_distance:.1f}km) - use {buses_needed} bus(es) to serve all"
            min_buses = 1
    
    print(f"   💡 Recommendation: {recommendation}\n")
    
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


def optimize_routes(school: Dict, students: List[Dict], max_buses: int, api_key: str) -> Dict:
    """
    Optimize bus routes using Google OR-Tools CVRP solver
    
    Strategy:
    1. Analyze student distribution to find hot spots
    2. If clusters are far apart (>7km), assign one bus per cluster
    3. Otherwise, try different bus counts and pick the best
    """
    if not school or not students:
        return {
            'routes': [],
            'total_buses': 0,
            'error': 'School location or students not set'
        }
    
    # STEP 1: Analyze clusters to get smart recommendation
    cluster_analysis = analyze_student_clusters(students, school)
    recommended_buses = cluster_analysis['recommended_buses']
    cluster_visualization = cluster_analysis.get('visualization', {})
    avg_cluster_distance = cluster_analysis.get('avg_cluster_distance', 0)
    n_clusters = cluster_analysis.get('n_clusters', 0)
    cluster_info = cluster_analysis.get('cluster_info', [])
    isolated_students = cluster_analysis.get('isolated_students', [])
    
    print(f"📊 Cluster analysis: {n_clusters} clusters, avg distance: {avg_cluster_distance:.1f}km")
    print(f"   Recommends {recommended_buses} buses")
    if isolated_students:
        print(f"   ⚠️  {len(isolated_students)} isolated students will be assigned to nearest cluster")
    
    # STEP 2: If clusters are far apart (>7km), use cluster-based routing
    if avg_cluster_distance > 7 and n_clusters > 1:
        print(f"\n🎯 Clusters are FAR APART ({avg_cluster_distance:.1f}km)")
        print(f"   Using cluster-based routing: 1+ bus per cluster\n")
        
        # Assign isolated students to nearest cluster
        if isolated_students:
            for iso_student in isolated_students:
                # Find nearest cluster
                min_dist = float('inf')
                nearest_cluster_idx = 0
                
                for idx, cluster in enumerate(cluster_info):
                    center = cluster['center']
                    dist = haversine_distance(
                        iso_student['latitude'], iso_student['longitude'],
                        center[0], center[1]
                    )
                    if dist < min_dist:
                        min_dist = dist
                        nearest_cluster_idx = idx
                
                # Add to nearest cluster
                cluster_info[nearest_cluster_idx]['students'].append(iso_student)
                print(f"   Assigned {iso_student['name']} to Cluster {nearest_cluster_idx + 1} ({min_dist:.1f}km away)")
        
        all_routes = []
        total_distance = 0
        max_route_time = 0
        bus_number = 1
        
        # Assign buses to each cluster
        for cluster_idx, cluster in enumerate(cluster_info):
            cluster_students = cluster['students']
            cluster_size = len(cluster_students)
            
            # Calculate buses needed for this cluster (max 40 students per bus)
            buses_for_cluster = max(1, math.ceil(cluster_size / 40))
            
            print(f"=== Cluster {cluster_idx + 1}: {cluster_size} students, needs {buses_for_cluster} bus(es) ===")
            
            # Solve CVRP for this cluster
            result = solve_cvrp(school, cluster_students, buses_for_cluster, api_key)
            
            if 'error' not in result and result['routes']:
                for route in result['routes']:
                    all_routes.append(route)
                    bus_number += 1
                total_distance += result['total_distance']
                max_route_time = max(max_route_time, result['max_route_time'])
        
        if all_routes:
            return {
                'routes': all_routes,
                'total_buses': len(all_routes),
                'max_route_time_minutes': round(max_route_time / 60, 1),
                'total_distance_km': round(total_distance, 2),
                'optimization_note': f"Using {len(all_routes)} bus(es) - cluster-based routing ({n_clusters} clusters, {avg_cluster_distance:.1f}km apart)",
                'cluster_visualization': cluster_visualization
            }
    
    # STEP 3: Otherwise, try different bus counts and pick the best
    print(f"\n📊 Clusters are close or single cluster - trying different bus counts\n")
    
    results = []
    
    # Try 1 bus
    print(f"=== Trying 1 bus ===")
    try:
        result = solve_cvrp(school, students, 1, api_key)
        if 'error' not in result and result['routes']:
            results.append({
                'num_buses': result['num_buses'],
                'routes': result['routes'],
                'max_time': result['max_route_time'],
                'total_distance': result['total_distance']
            })
    except Exception as e:
        print(f"Error with 1 bus: {e}")
    
    # Try recommended number if > 1
    if recommended_buses > 1:
        for num_buses in range(2, min(max_buses, recommended_buses) + 1):
            print(f"\n=== Trying {num_buses} buses ===")
            try:
                result = solve_cvrp(school, students, num_buses, api_key)
                if 'error' not in result and result['routes']:
                    results.append({
                        'num_buses': result['num_buses'],
                        'routes': result['routes'],
                        'max_time': result['max_route_time'],
                        'total_distance': result['total_distance']
                    })
            except Exception as e:
                print(f"Error with {num_buses} buses: {e}")
    
    if not results:
        return {'routes': [], 'total_buses': 0, 'error': 'Could not create routes', 'cluster_visualization': cluster_visualization}
    
    # Pick best solution
    min_time = min(r['max_time'] for r in results)
    
    # If best time > 30 minutes, prioritize time
    if min_time > 1800:
        best = min(results, key=lambda x: x['max_time'])
        return {
            'routes': best['routes'],
            'total_buses': best['num_buses'],
            'max_route_time_minutes': round(best['max_time'] / 60, 1),
            'total_distance_km': round(best['total_distance'], 2),
            'optimization_note': f"Using {best['num_buses']} bus(es) - prioritizing speed",
            'cluster_visualization': cluster_visualization
        }
    
    # Otherwise, prefer fewer buses within 15% of minimum time
    threshold = min_time * 1.15
    results_sorted = sorted(results, key=lambda x: x['num_buses'])
    
    for result in results_sorted:
        if result['max_time'] <= threshold:
            return {
                'routes': result['routes'],
                'total_buses': result['num_buses'],
                'max_route_time_minutes': round(result['max_time'] / 60, 1),
                'total_distance_km': round(result['total_distance'], 2),
                'optimization_note': f"Using {result['num_buses']} bus(es) - optimal balance",
                'cluster_visualization': cluster_visualization
            }
    
    # Fallback
    best = min(results, key=lambda x: x['max_time'])
    return {
        'routes': best['routes'],
        'total_buses': best['num_buses'],
        'max_route_time_minutes': round(best['max_time'] / 60, 1),
        'total_distance_km': round(best['total_distance'], 2),
        'cluster_visualization': cluster_visualization
    }


# Remove old clustering function - OR-Tools handles this automatically
