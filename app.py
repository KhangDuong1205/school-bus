from flask import Flask, render_template, request, jsonify
import requests
from typing import List, Dict, Tuple
import math
import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school_bus.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Import and initialize database
from models import db, RouteHistory, VehicleType, Vehicle
db.init_app(app)

# Create tables on first request
with app.app_context():
    db.create_all()

@dataclass
class RouteSegment:
    from_lat: float
    from_lng: float
    to_lat: float
    to_lng: float
    distance: float
    duration: float  # in seconds

# Get API key from environment variable (secure)
API_KEY = os.environ.get('ONEMAP_API_KEY')

if not API_KEY:
    raise ValueError(
        "ONEMAP_API_KEY environment variable not set!\n"
        "Please create a .env file with your API key or set the environment variable.\n"
        "Get your API key from: https://www.onemap.gov.sg/apidocs/"
    )

# In-memory storage (will use database later)
students = []
school_location = None
optimized_routes = []

# Constants
MAX_STUDENTS_PER_BUS = 40
AVERAGE_PICKUP_TIME = 60  # seconds per student pickup

# CSV file path for default students
STUDENT_CSV_PATH = os.path.join(os.path.dirname(__file__), 'student-data', 'swat XCL dan test upload - Sheet1.csv')

def load_students_from_csv():
    """Load students from CSV file and set school location from drop-off coordinates"""
    global school_location
    loaded_students = []
    
    if not os.path.exists(STUDENT_CSV_PATH):
        print(f"CSV file not found: {STUDENT_CSV_PATH}")
        return loaded_students
    
    try:
        with open(STUDENT_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                # Extract student data from CSV columns
                # User Requirement: Capture student_id and remark
                student_id = row.get('student_id', row.get('ID', str(idx)))
                name = row.get('ID', f'Student {idx}')  # Keep existing logic for name for now
                
                address = row.get('Pick-up address line 1', '')
                address_2 = row.get('Pick-up address line 2', '')
                if address_2 and address_2 != 'Null':
                    address = f"{address}, {address_2}"
                
                # Check for 'remark' field
                remark = row.get('remark', row.get('Remark', ''))
                
                latitude = row.get('latitude', row.get('Pick-up latitude', ''))
                longitude = row.get('longitude', row.get('Pick-up longitude', ''))
                
                # Skip rows with missing coordinates
                if not latitude or not longitude:
                    continue
                
                # Extract school location from first row's drop-off coordinates
                if school_location is None:
                    drop_off_lat = row.get('Drop-off latitude', '')
                    drop_off_lng = row.get('Drop-off longitude', '')
                    drop_off_address = row.get('Drop-off address line 1', '')
                    
                    if drop_off_lat and drop_off_lng:
                        try:
                            school_location = {
                                'name': 'School',
                                'address': drop_off_address,
                                'postal': '',
                                'latitude': float(drop_off_lat),
                                'longitude': float(drop_off_lng)
                            }
                            print(f"School location set from CSV: {drop_off_address} ({drop_off_lat}, {drop_off_lng})")
                        except ValueError:
                            pass
                
                try:
                    student = {
                        'id': idx,  # Internal ID for UI
                        'student_id': student_id, # Original ID from CSV
                        'name': name,
                        'address': address,
                        'postal': '',  # CSV doesn't have postal code
                        'address_note': remark, # Store remark
                        'latitude': float(latitude),
                        'longitude': float(longitude)
                    }
                    loaded_students.append(student)
                except ValueError:
                    # Skip rows with invalid coordinates
                    continue
        
        print(f"Loaded {len(loaded_students)} students from CSV")
    except Exception as e:
        print(f"Error loading CSV: {e}")
    
    return loaded_students

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def search_address():
    """Search for address using OneMap API - returns all results"""
    data = request.json
    search_val = data.get('searchVal')
    
    if not search_val:
        return jsonify({'error': 'Search value is required'}), 400
    
    url = f'https://www.onemap.gov.sg/api/common/elastic/search'
    params = {
        'searchVal': search_val,
        'returnGeom': 'Y',
        'getAddrDetails': 'Y',
        'pageNum': 1
    }
    headers = {
        'Authorization': API_KEY
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        result = response.json()
        
        if result.get('found', 0) > 0:
            return jsonify({'results': result['results'], 'found': result['found']})
        else:
            return jsonify({'results': [], 'found': 0})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/students', methods=['GET'])
def get_students():
    """Get all students"""
    return jsonify(students)

@app.route('/api/students', methods=['POST'])
def add_student():
    """Add a new student"""
    data = request.json
    
    student = {
        'id': len(students) + 1,
        'name': data['name'],
        'address': data['address'],
        'postal': data['postal'],
        'latitude': float(data['latitude']),
        'longitude': float(data['longitude'])
    }
    
    students.append(student)
    return jsonify(student), 201

@app.route('/api/students/<int:student_id>', methods=['DELETE'])
def delete_student(student_id):
    """Delete a student"""
    global students
    students = [s for s in students if s['id'] != student_id]
    return jsonify({'success': True})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics"""
    total_students = len(students)
    buses_needed = math.ceil(total_students / 40) if total_students > 0 else 0
    
    return jsonify({
        'total_students': total_students,
        'buses_needed': buses_needed
    })

@app.route('/api/school', methods=['GET'])
def get_school():
    """Get school location"""
    return jsonify(school_location)


@app.route('/api/analyze-clusters', methods=['GET'])
def analyze_clusters():
    """Analyze student clusters and return visualization data"""
    print(f"\n=== Analyze Clusters Request ===")
    print(f"Number of students: {len(students)}")
    print(f"School location set: {school_location is not None}")
    
    if not students:
        print("No students - returning empty clusters")
        return jsonify({'clusters': []})
    
    if not school_location:
        print("No school location - returning empty clusters")
        return jsonify({'clusters': []})
    
    from route_optimizer import analyze_student_clusters
    
    analysis = analyze_student_clusters(students, school_location)
    
    clusters = analysis.get('visualization', {}).get('clusters', [])
    isolated = analysis.get('visualization', {}).get('isolated', [])
    print(f"Clusters found: {len(clusters)}")
    for i, cluster in enumerate(clusters):
        print(f"  Cluster {i+1}: {cluster['size']} students, center: ({cluster['center']['lat']:.4f}, {cluster['center']['lng']:.4f}), radius: {cluster['radius']:.0f}m")
    
    if isolated:
        print(f"Isolated students: {len(isolated)}")
        for iso in isolated:
            print(f"  - {iso['name']}")
    
    result = {
        'clusters': clusters,
        'isolated': isolated,
        'n_clusters': analysis.get('n_clusters', 0),
        'n_noise': analysis.get('n_noise', 0),
        'recommended_buses': analysis.get('recommended_buses', 1),
        'recommendation': analysis.get('recommendation', '')
    }
    
    print(f"Returning: {len(result['clusters'])} clusters, {len(result['isolated'])} isolated")
    return jsonify(result)


@app.route('/api/analyze-clusters', methods=['POST'])
def analyze_clusters_endpoint():
    """Analyze student clusters without running full optimization"""
    from route_optimizer import analyze_student_clusters
    
    if not school_location:
        return jsonify({'error': 'Please set school location first'}), 400
    
    if not students or len(students) == 0:
        return jsonify({'error': 'Please add students first'}), 400
    
    print(f"\n=== Analyze Clusters Request ===")
    print(f"School location: {school_location.get('address', 'Unknown')}")
    print(f"Number of students: {len(students)}")
    
    # Run cluster analysis
    result = analyze_student_clusters(students, school_location)
    
    # Format response with cluster visualization data
    clusters = []
    for cluster in result.get('cluster_info', []):
        clusters.append({
            'id': cluster['id'],
            'size': cluster['size'],
            'center': {'lat': cluster['center'][0], 'lng': cluster['center'][1]},
            'distance_from_school': round(cluster['distance_from_school'], 2),
            'students': [{'name': s['name'], 'lat': s['latitude'], 'lng': s['longitude']} 
                        for s in cluster['students']]
        })
    
    isolated = [{'name': s['name'], 'lat': s['latitude'], 'lng': s['longitude']} 
                for s in result.get('isolated_students', [])]
    
    return jsonify({
        'n_clusters': result.get('n_clusters', len(clusters)),
        'clusters': clusters,
        'isolated_students': isolated,
        'recommended_buses': result.get('recommended_buses', 1),
        'total_students': len(students)
    })


@app.route('/api/optimise-routes', methods=['POST'])
def optimise_routes_endpoint():
    """Optimise bus routes"""
    from route_optimizer import optimize_routes
    
    data = request.json
    max_buses = int(data.get('max_buses', 3))
    school_time = data.get('school_time', '07:30')  # Default 7:30 AM
    max_ride_time = int(data.get('max_ride_time', 60))  # Default 60 minutes
    
    # Convert school_time (HH:MM) to seconds from midnight
    try:
        hours, minutes = map(int, school_time.split(':'))
        school_arrival_seconds = hours * 3600 + minutes * 60
    except:
        school_arrival_seconds = 27000  # Default 7:30 AM
    
    print(f"\n=== Optimise Routes Request ===")
    print(f"Max buses: {max_buses}")
    print(f"School time: {school_time} ({school_arrival_seconds}s)")
    print(f"Max ride time: {max_ride_time} min")
    print(f"School location: {school_location is not None}")
    print(f"Number of students: {len(students)}")
    
    if not school_location:
        print("ERROR: No school location set")
        return jsonify({'error': 'Please set school location first'}), 400
    
    if not students or len(students) == 0:
        print("ERROR: No students added")
        return jsonify({'error': 'Please add students first'}), 400
    
    import traceback
    import traceback
    try:
        # Fetch active vehicles for fleet-aware optimization
        # We need them primarily for capacities, but will use their IDs for assignment later
        active_vehicles = Vehicle.query.filter_by(status='active').order_by(Vehicle.id).all()
        
        # Extract capacities (default to 40 if 0/None)
        fleet_capacities = [v.capacity if v.capacity and v.capacity > 0 else 40 for v in active_vehicles]
        
        # Pass fleet_capacities to optimizer
        result = optimize_routes(school_location, students, max_buses, API_KEY, 
                                school_arrival_seconds, max_ride_time,
                                fleet_capacities=fleet_capacities)
        
        # Inject context for saving/restoring history
        result['school'] = school_location
        result['all_students'] = students
        
        print(f"\n=== Optimization complete ===")
        print(f"Routes: {len(result.get('routes', []))}, Error: {result.get('error', 'None')}")
    except Exception as e:
        print(f"\n!!! OPTIMIZATION CRASHED !!!")
        traceback.print_exc()
        result = {'error': str(e), 'routes': []}
    
    # --- Assign Real Bus IDs ---
    try:
        if result.get('routes'):
            # Fetch active vehicles (if not already fetched above, but strictly we should use the same list)
            # We already fetched 'active_vehicles' above.
            
            for i, route in enumerate(result['routes']):
                # Determine which vehicle from the fleet this route belongs to
                # The optimizer returns 'vehicle_index' if it used a specific fleet vehicle.
                # If missing (legacy/fallback), assume 1:1 mapping with loop index.
                fleet_idx = route.get('vehicle_index', i)
                
                # If we have a real vehicle available at this index
                if 0 <= fleet_idx < len(active_vehicles):
                    vehicle = active_vehicles[fleet_idx]
                    route['bus_number'] = f"Bus {i + 1}"
                    route['vehicle_plate'] = vehicle.plate_number
                    route['vehicle_id'] = vehicle.id
                    route['vehicle_capacity'] = vehicle.capacity
                else:
                    # Fallback for virtual/extra buses
                    route['bus_number'] = f"Bus {i + 1}"
                    route['vehicle_plate'] = "Pending"
                    route['vehicle_id'] = ""
            
            print(f"Assigned real vehicles to {len(result['routes'])} routes.")
    except Exception as e:
        print(f"Error assigning vehicle IDs: {e}")
        import traceback
        traceback.print_exc()
        # Ensure result is still returned even if assignment fails
    # ---------------------------
    
    return jsonify(result)


@app.route('/api/load-students-csv', methods=['POST'])
def load_students_csv_endpoint():
    """Load students from the CSV file"""
    global students
    
    loaded = load_students_from_csv()
    students.extend(loaded)
    
    return jsonify({
        'success': True,
        'loaded': len(loaded),
        'total_students': len(students)
    })


@app.route('/api/cache/stats', methods=['GET'])
def get_cache_stats_endpoint():
    """Get cache statistics"""
    from route_optimizer import get_cache_stats
    stats = get_cache_stats()
    return jsonify(stats)


@app.route('/api/cache/clear', methods=['POST'])
def clear_cache_endpoint():
    """Clear the distance cache"""
    from route_optimizer import clear_cache
    clear_cache()
    return jsonify({'success': True, 'message': 'Cache cleared successfully'})


# ============ Route History CRUD Endpoints ============

@app.route('/api/runs', methods=['GET'])
def list_runs():
    """List all saved route optimization runs"""
    runs = RouteHistory.query.order_by(RouteHistory.timestamp.desc()).all()
    return jsonify([run.to_summary_dict() for run in runs])


@app.route('/api/runs', methods=['POST'])
def save_run():
    """Save a route optimization run"""
    data = request.json
    if not data or 'result_json' not in data:
        return jsonify({'error': 'Missing result_json'}), 400
    
    # Auto-generate name if not provided
    name = data.get('name', f"Run {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Generate summary from result
    result = data['result_json']
    routes = result.get('routes', [])
    total_students = sum(r.get('student_count', 0) for r in routes)
    total_distance = result.get('total_distance_km', 0)
    summary = f"{len(routes)} Buses, {total_distance}km, {total_students} Students"
    
    run = RouteHistory(
        name=name,
        summary=summary,
        result_json=result,
        input_params=data.get('input_params')
    )
    db.session.add(run)
    db.session.commit()
    
    return jsonify({'success': True, 'id': run.id, 'name': run.name})


@app.route('/api/runs/<int:run_id>', methods=['GET'])
def get_run(run_id):
    """Get a specific saved run by ID"""
    run = RouteHistory.query.get_or_404(run_id)
    return jsonify(run.to_dict())


@app.route('/api/runs/<int:run_id>', methods=['DELETE'])
def delete_run(run_id):
    """Delete a saved run"""
    run = RouteHistory.query.get_or_404(run_id)
    db.session.delete(run)
    db.session.commit()
    return jsonify({'success': True, 'message': f'Run {run_id} deleted'})


# ============ Vehicle Type CRUD Endpoints ============

@app.route('/api/vehicle-types', methods=['GET'])
def list_vehicle_types():
    """List all vehicle types"""
    types = VehicleType.query.all()
    return jsonify([t.to_dict() for t in types])


@app.route('/api/vehicle-types', methods=['POST'])
def create_vehicle_type():
    """Create a new vehicle type"""
    data = request.json
    if not data or 'name' not in data or 'capacity' not in data:
        return jsonify({'error': 'name and capacity are required'}), 400
    
    vtype = VehicleType(
        name=data['name'],
        routing_profile=data.get('routing_profile', 'van'),
        capacity=int(data['capacity']),
        label=data.get('label', '')
    )
    db.session.add(vtype)
    db.session.commit()
    return jsonify(vtype.to_dict()), 201


@app.route('/api/vehicle-types/<int:type_id>', methods=['PUT'])
def update_vehicle_type(type_id):
    """Update a vehicle type"""
    vtype = VehicleType.query.get_or_404(type_id)
    data = request.json
    
    if 'name' in data:
        vtype.name = data['name']
    if 'routing_profile' in data:
        vtype.routing_profile = data['routing_profile']
    if 'capacity' in data:
        vtype.capacity = int(data['capacity'])
    if 'label' in data:
        vtype.label = data['label']
    
    db.session.commit()
    return jsonify(vtype.to_dict())


@app.route('/api/vehicle-types/<int:type_id>', methods=['DELETE'])
def delete_vehicle_type(type_id):
    """Delete a vehicle type"""
    vtype = VehicleType.query.get_or_404(type_id)
    db.session.delete(vtype)
    db.session.commit()
    return jsonify({'success': True})


# ============ Vehicle CRUD Endpoints ============

@app.route('/api/vehicles', methods=['GET'])
def list_vehicles():
    """List all vehicles"""
    vehicles = Vehicle.query.all()
    return jsonify([v.to_dict() for v in vehicles])


@app.route('/api/vehicles', methods=['POST'])
def create_vehicle():
    """Create a new vehicle with unique ID based on type"""
    data = request.json
    if not data or 'plate_number' not in data:
        return jsonify({'error': 'plate_number is required'}), 400
    if not data.get('type_id'):
        return jsonify({'error': 'type_id is required'}), 400
    
    # Get vehicle type
    vtype = VehicleType.query.get(data['type_id'])
    if not vtype:
        return jsonify({'error': 'Invalid vehicle type'}), 400
    
    # Generate ID: {CODE}{CAPACITY}-{NEXT_NUMBER}
    # e.g., MB20-01, SB30-02
    existing_count = Vehicle.query.filter_by(type_id=vtype.id).count()
    next_num = existing_count + 1
    unique_id = f"{vtype.code}{vtype.capacity}-{next_num:02d}"
    
    vehicle = Vehicle(
        id=unique_id,
        plate_number=data['plate_number'],
        nickname=data.get('nickname', ''),
        driver_name=data.get('driver_name', ''),
        status=data.get('status', 'active'),
        type_id=vtype.id
    )
    db.session.add(vehicle)
    db.session.commit()
    return jsonify(vehicle.to_dict()), 201


@app.route('/api/vehicles/<vehicle_id>', methods=['PUT'])
def update_vehicle(vehicle_id):
    """Update a vehicle"""
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    data = request.json
    
    if 'plate_number' in data:
        vehicle.plate_number = data['plate_number']
    if 'nickname' in data:
        vehicle.nickname = data['nickname']
    if 'driver_name' in data:
        vehicle.driver_name = data['driver_name']
    if 'status' in data:
        vehicle.status = data['status']
    if 'type_id' in data:
        vehicle.type_id = data['type_id']
    
    db.session.commit()
    return jsonify(vehicle.to_dict())


@app.route('/api/vehicles/<vehicle_id>', methods=['DELETE'])
def delete_vehicle(vehicle_id):
    """Delete a vehicle"""
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    db.session.delete(vehicle)
    db.session.commit()
    return jsonify({'success': True})


# ============ Fleet Summary Endpoint ============

@app.route('/api/fleet-summary', methods=['GET'])
def fleet_summary():
    """Get summary of available fleet for optimization"""
    # Get all active vehicles with their types
    active_vehicles = Vehicle.query.filter_by(status='active').all()
    
    total_capacity = 0
    for v in active_vehicles:
        if v.vehicle_type:
            total_capacity += v.vehicle_type.capacity
        else:
            total_capacity += 40  # Default capacity if no type assigned
    
    return jsonify({
        'total_vehicles': Vehicle.query.count(),
        'active_vehicles': len(active_vehicles),
        'total_capacity': total_capacity
    })

# ============ Page Routes ============

@app.route('/vehicle-types')
def vehicle_types_page():
    """Vehicle Types management page"""
    return render_template('vehicle_types.html')


@app.route('/vehicles')
def vehicles_page():
    """Fleet management page"""
    return render_template('vehicles.html')


@app.route('/api/export-routes-csv', methods=['POST'])
def export_routes_csv():
    """
    Export optimized routes to CSV/JSON with:
    student_id, postal_code, address_note, pickup_time, route_name
    """
    try:
        data = request.json
        routes = data.get('routes', [])
        format_type = request.args.get('format', 'csv') # 'csv' or 'json'
        
        if not routes:
            return jsonify({'error': 'No routes data provided'}), 400
        
        # Helper to find student by name
        # Create a lookup map for speed and accuracy
        student_map = {s['name']: s for s in students}
        
        # Helper to format time
        def format_time_str(seconds_from_midnight):
            h = int(seconds_from_midnight // 3600) % 24
            m = int(seconds_from_midnight % 3600) // 60
            period = "AM" if h < 12 else "PM"
            display_h = h if h <= 12 else h - 12
            if display_h == 0: display_h = 12
            return f"{display_h}:{m:02d} {period}"

        # Import get_postal_code from route_optimizer
        # We do this here to avoid circular imports at top level
        from route_optimizer import get_postal_code
        
        # Ensure API_KEY is available
        api_key_to_use = API_KEY
        if not api_key_to_use:
            print("WARNING: API_KEY not set for export")

        # Consolidate results for both CSV and JSON
        export_data = []

        # ... (Header for CSV moved below loop)
        
        # School Arrival Time (default 7:30 AM = 27000s)
        # ideally this comes from input params, but we can infer or default
        SCHOOL_ARRIVAL_TARGET = 27000 
        # Actually, let's deduce from route total time if possible, or use the default.
        # The user's goal is relative order and time.
        
        for route_idx, route in enumerate(routes):
            route_name = route.get('bus_number', f"Bus {route_idx + 1}")
            vehicle_id = route.get('vehicle_id', '')
            vehicle_plate = route.get('vehicle_plate', '')
            
            # Calculate start time
            # School Arrival (Target) - Total Duration = Start Time
            # Note: This assumes the route is tight to arrival time.
            total_duration = route.get('total_time_seconds', 0)
            if not total_duration:
                # Fallback if total_time_seconds missing
                total_duration = route.get('max_route_time', 0) 
            
            # Start time of the bus (leaving creation point/school)
            current_time = SCHOOL_ARRIVAL_TARGET - total_duration
            
            segments = route.get('segments', [])
            
            for seg in segments:
                # Add travel time to current time
                duration = seg.get('time', 0)
                current_time += duration
                
                # If this segment ends at a student, record pickup
                student_name = seg.get('student')
                if student_name and student_name != 'School' and student_name != 'Return to School':
                    student_obj = student_map.get(student_name)
                    
                    if student_obj:
                        s_id = student_obj.get('student_id', student_obj.get('id', ''))
                        remark = student_obj.get('address_note', '')
                        lat = student_obj.get('latitude')
                        lng = student_obj.get('longitude')
                        address = student_obj.get('address', '')
                        
                        # Reverse Geocode
                        postal = ''
                        try:
                            if api_key_to_use:
                                postal = get_postal_code(lat, lng, api_key_to_use)
                        except Exception as geo_err:
                            print(f"Geocoding error for {student_name}: {geo_err}")
                            postal = ''
                        
                        # Pickup Time
                        pickup_str = format_time_str(current_time)
                        
                        export_data.append({
                            'student_id': s_id,
                            'postal_code': postal,
                            'address_note': remark,
                            'pickup_time': pickup_str,
                            'route_name': route_name,
                            'vehicle_id': vehicle_id,
                            'vehicle_plate': vehicle_plate,
                            'student_name': student_name,
                            'address': address
                        })
                    else:
                        # Student not found
                         export_data.append({
                            'student_id': 'Unknown',
                            'postal_code': '',
                            'address_note': '',
                            'pickup_time': format_time_str(current_time),
                            'route_name': route_name,
                            'vehicle_id': vehicle_id,
                            'vehicle_plate': vehicle_plate,
                            'student_name': student_name,
                            'address': ''
                        })

        if format_type == 'json':
            return jsonify({'data': export_data})
        
        # CSV FORMAT
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Bus Number', 'Vehicle ID', 'Plate Number', 'Student ID', 'Postal Code', 'Remark', 'Pickup Time', 'Student Name', 'Address'])
        
        for item in export_data:
             writer.writerow([
                 item['route_name'],
                 item['vehicle_id'],
                 item['vehicle_plate'],
                 item['student_id'],
                 item['postal_code'],
                 item['address_note'],
                 item['pickup_time'],
                 item['student_name'],
                 item['address']
             ])

        # Create response
        output.seek(0)
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=optimized_routes.csv"}
        )

    except Exception as e:
        print(f"Export CSV Error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)



