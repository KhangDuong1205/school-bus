def optimize_routes(school: Dict, students: List[Dict], max_buses: int, api_key: str,
                   max_ride_time_minutes: int = 60) -> Dict:
    """
    Optimize bus routes using Google OR-Tools CVRP solver
    
    Strategy:
    1. Validate inputs and check feasibility
    2. Analyze student distribution for visualization
    3. Try different bus counts and pick the best valid solution
    """
    # STEP 0: Input validation
    if not school or not students:
        return {
            'routes': [],
            'total_buses': 0,
            'error': 'School location or students not set'
        }
    
    if max_buses < 1:
        return {'error': 'max_buses must be at least 1'}
    
    if not api_key or api_key.strip() == '':
        return {'error': 'API key is required'}
    
    # Validate coordinates
    for student in students:
        if not (-90 <= student.get('latitude', 999) <= 90):
            return {'error': f"Invalid latitude for {student.get('name', 'unknown')}"}
        if not (-180 <= student.get('longitude', 999) <= 180):
            return {'error': f"Invalid longitude for {student.get('name', 'unknown')}"}
    
    if not (-90 <= school.get('latitude', 999) <= 90):
        return {'error': 'Invalid school latitude'}
    if not (-180 <= school.get('longitude', 999) <= 180):
        return {'error': 'Invalid school longitude'}
    
    # Invalidate cache if school location changed
    invalidate_cache_if_school_changed(school)
    
    # STEP 1: Feasibility check
    min_buses_capacity = max(1, math.ceil(len(students) / 40))
    
    # Estimate minimum buses for time constraint
    max_distance = max(
        haversine_distance(school['latitude'], school['longitude'],
                          s['latitude'], s['longitude'])
        for s in students
    )
    estimated_longest_route = estimate_travel_time(max_distance * 2)
    min_buses_time = math.ceil(estimated_longest_route / (max_ride_time_minutes * 60))
    
    min_buses_needed = max(min_buses_capacity, min_buses_time)
    
    if max_buses < min_buses_needed:
        return {
            'error': f'Need at least {min_buses_needed} buses (you provided {max_buses})',
            'reason': 'Capacity or time constraints cannot be met'
        }
    
    # STEP 2: Analyze clusters for visualization
    cluster_analysis = analyze_student_clusters(students, school)
    recommended_buses = cluster_analysis['recommended_buses']
    cluster_visualization = cluster_analysis.get('visualization', {})
    
    print(f"📊 Cluster analysis recommends {recommended_buses} buses")
    print(f"   Minimum needed: {min_buses_needed} (capacity: {min_buses_capacity}, time: {min_buses_time})")
    print(f"   Will try up to {min(max_buses, recommended_buses)} buses\n")
    
    # STEP 3: Try different bus counts
    print(f"🚌 Trying different bus counts (CVRP handles all routing)\n")
    
    results = []
    
    # Try from minimum to recommended (capped at max_buses)
    for num_buses in range(min_buses_needed, min(max_buses, recommended_buses) + 1):
        print(f"=== Trying {num_buses} bus(es) ===")
        try:
            result = solve_cvrp(school, students, num_buses, api_key,
                              max_route_time_minutes=max_ride_time_minutes,
                              school_arrival_time=27000,  # 7:30 AM
                              max_ride_time_minutes=max_ride_time_minutes)
            
            if 'error' not in result and result['routes']:
                # Check for time violations
                violations = result.get('time_violations', [])
                
                if violations:
                    print(f"  ⚠️  {len(violations)} time violations - need more buses")
                    # Don't add this result
                    continue
                
                # Valid solution - add it
                print(f"  ✅ No time violations!")
                results.append({
                    'num_buses': result['num_buses'],
                    'routes': result['routes'],
                    'max_time': result['max_route_time'],
                    'total_distance': result['total_distance'],
                    'max_student_ride_time': result.get('max_student_ride_time', 0)
                })
                
        except Exception as e:
            print(f"  ✗ Error with {num_buses} buses: {e}")
    
    if not results:
        return {
            'routes': [],
            'total_buses': 0,
            'error': 'Could not create valid routes (try increasing max_buses)',
            'cluster_visualization': cluster_visualization
        }
    
    # STEP 4: Pick best solution
    # Prefer solutions with acceptable ride times (<45 min)
    acceptable = [r for r in results if r.get('max_student_ride_time', r['max_time']) < 2700]  # 45 min
    
    if acceptable:
        # Among acceptable, prefer fewer buses
        best = min(acceptable, key=lambda x: x['num_buses'])
        note = f"Using {best['num_buses']} bus(es) - balanced solution"
    else:
        # No "great" solutions - prioritize speed
        best = min(results, key=lambda x: x.get('max_student_ride_time', x['max_time']))
        note = f"Using {best['num_buses']} bus(es) - prioritizing speed"
    
    return {
        'routes': best['routes'],
        'total_buses': best['num_buses'],
        'max_route_time_minutes': round(best['max_time'] / 60, 1),
        'max_student_ride_time_minutes': round(best.get('max_student_ride_time', best['max_time']) / 60, 1),
        'total_distance_km': round(best['total_distance'], 2),
        'optimization_note': note,
        'cluster_visualization': cluster_visualization
    }
