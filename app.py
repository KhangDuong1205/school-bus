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

from onemap_utils import get_onemap_token

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

# Pre-load the local OSM graph in a background thread so the first
# "fetch geometry" request doesn't pay the ~3s graph-load cost.
def _warm_local_routing():
    try:
        from local_routing import warmup
        warmup()
    except Exception as e:
        print(f"[startup] local_routing warmup failed: {e}")

import threading
threading.Thread(target=_warm_local_routing, daemon=True).start()

@dataclass
class RouteSegment:
    from_lat: float
    from_lng: float
    to_lat: float
    to_lng: float
    distance: float
    duration: float  # in seconds

def get_api_key():
    """Dynamically fetch the OneMap API key (handles auto-reset)"""
    try:
        return get_onemap_token()
    except Exception as e:
        print(f"Error getting OneMap token: {e}")
        return None

# Initial check for API credentials
if not os.environ.get('ONEMAP_API_KEY') and not (os.environ.get('ONEMAP_EMAIL') and os.environ.get('ONEMAP_PASSWORD')):
    print("WARNING: OneMap credentials not set! Please configure ONEMAP_EMAIL and ONEMAP_PASSWORD in .env")

# Legacy constant for backwards compatibility where necessary
# But we should prefer get_api_key()
API_KEY = get_api_key()

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
    """Load students from CSV file (students only, school location is set via Settings)"""
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
                name = row.get("Sender's first name", row.get('Name', row.get('name', row.get('student_name', ''))))
                
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
                
                try:
                    student = {
                        'id': idx,  # Internal ID for UI
                        'student_id': student_id, # Original ID from CSV
                        'name': name,
                        'address': address,
                        'postal': '',  # CSV doesn't have postal code
                        'address_note': remark, # Store remark
                        'latitude': float(latitude),
                        'longitude': float(longitude),
                        'family_code': str(row.get('family_code', row.get('Family Code', ''))),
                        'special_needs': str(row.get('special_needs', row.get('Special Needs', ''))).lower() in ['true', 'yes', '1', 'y']
                    }
                    loaded_students.append(student)
                except ValueError:
                    # Skip rows with invalid coordinates
                    continue
        
        print(f"Loaded {len(loaded_students)} students from CSV")
    except Exception as e:
        print(f"Error loading CSV: {e}")
    
    return loaded_students

@app.before_request
def refresh_api_key():
    """Ensure API_KEY is fresh before each request"""
    global API_KEY
    API_KEY = get_api_key()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/export-data')
def export_data():
    return render_template('export_data.html')

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
    
    key = get_api_key()
    if not key:
        return jsonify({'error': 'OneMap API key not configured'}), 500
        
    headers = {
        'Authorization': key
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
        'longitude': float(data['longitude']),
        'family_code': str(data.get('family_code', '')),
        'special_needs': bool(data.get('special_needs', False))
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


@app.route('/api/school', methods=['PUT'])
def set_school():
    """Set school location from Settings page"""
    global school_location
    data = request.json
    
    if not data or 'latitude' not in data or 'longitude' not in data:
        return jsonify({'error': 'latitude and longitude are required'}), 400
    
    try:
        school_location = {
            'name': data.get('name', 'School'),
            'address': data.get('address', ''),
            'postal': data.get('postal', ''),
            'latitude': float(data['latitude']),
            'longitude': float(data['longitude'])
        }
        print(f"School location set from Settings: {school_location['address']} ({school_location['latitude']}, {school_location['longitude']})")
        return jsonify({'success': True, 'school': school_location})
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid coordinates: {e}'}), 400


@app.route('/api/optimise-routes', methods=['POST'])
def optimise_routes_endpoint():
    """Optimise bus routes"""
    from route_optimizer import optimize_routes
    
    data = request.json
    max_buses = int(data.get('max_buses', 3))
    school_time = data.get('school_time', '07:30')  # Default 7:30 AM
    max_ride_time = int(data.get('max_ride_time', 60))  # Default 60 minutes
    
    # Advanced parameters
    service_time = int(data.get('service_time', 60))
    base_bus_cost = 5000  # Hardcoded default
    penalty_per_seat = 200  # Hardcoded default
    
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

        max_buses = len(active_vehicles) if active_vehicles else 1

        # Extract capacities (use the to_dict() logic which correctly checks VehicleType)
        fleet_capacities = [v.to_dict()['capacity'] for v in active_vehicles]

        # Package advanced parameters
        advanced_params = {
            'service_time': service_time,
            'base_bus_cost': base_bus_cost,
            'penalty_per_seat': penalty_per_seat
        }

        # Pass fleet_capacities and advanced_params to optimizer
        result = optimize_routes(school_location, students, max_buses, API_KEY,
                                school_arrival_seconds, max_ride_time,
                                fleet_capacities=fleet_capacities,
                                advanced_params=advanced_params)
        # Inject context for saving/restoring history
        result['school'] = school_location
        result['all_students'] = students
        
        print(f"\n=== Optimization complete ===")
        print(f"Routes: {len(result.get('routes', []))}, Error: {result.get('error', 'None')}")
    except Exception as e:
        print(f"\n!!! OPTIMIZATION CRASHED !!!")
        traceback.print_exc()
        result = {'error': str(e), 'routes': []}
    
    # --- Assign Real Bus IDs (Smart Capacity Matching) ---
    try:
        if result.get('routes'):
            # Fetch active vehicles
            active_vehicles = Vehicle.query.filter_by(status='active').all()
            
            # Create a pool of available vehicles, sorting by capacity ascending
            # This allows us to pick the smallest bus that fits the route
            available_vehicles = sorted([v.to_dict() for v in active_vehicles], key=lambda x: x['capacity'])
            
            # Sort routes by student count descending so we fulfill the biggest routes first
            routes_sorted = sorted(result['routes'], key=lambda r: r.get('student_count', len(r.get('students', []))), reverse=True)
            
            for i, route in enumerate(routes_sorted):
                student_count = route.get('student_count', len(route.get('students', [])))
                
                # Find the smallest available vehicle that can hold the students
                matched_vehicle = None
                for j, v in enumerate(available_vehicles):
                    if v['capacity'] >= student_count:
                        matched_vehicle = available_vehicles.pop(j)
                        break
                
                # If no vehicle is large enough, just take the largest available
                if not matched_vehicle and available_vehicles:
                    matched_vehicle = available_vehicles.pop(-1)
                
                if matched_vehicle:
                    route['bus_number'] = f"Bus {i + 1}"
                    route['vehicle_plate'] = matched_vehicle['plate_number']
                    route['vehicle_id'] = matched_vehicle['id']
                    route['vehicle_capacity'] = matched_vehicle['capacity']
                else:
                    # Fallback for virtual/extra buses if we ran out of fleet
                    route['bus_number'] = f"Bus {i + 1}"
                    route['vehicle_plate'] = "Pending"
                    route['vehicle_id'] = ""
                    route['vehicle_capacity'] = 40
            
            # Sort back to original (or some sensible order) so UI looks consistent
            # The UI sorts by distance or time, so it doesn't matter too much, but let's keep it sorted by pax
            result['routes'] = routes_sorted
            
            print(f"Assigned real vehicles to {len(result['routes'])} routes.")
    except Exception as e:
        print(f"Error assigning vehicle IDs: {e}")
        import traceback
        traceback.print_exc()
    # ---------------------------
    
    return jsonify(result)


@app.route('/api/recalculate-routes', methods=['POST'])
def recalculate_routes_endpoint():
    """Recalculate route times and distances after manual drag-and-drop tweaks"""
    from route_optimizer import recalculate_manually_adjusted_routes
    
    data = request.json
    routes = data.get('routes', [])
    school_time = data.get('school_time', '07:30')
    max_ride_time = int(data.get('max_ride_time', 60))
    service_time = int(data.get('service_time', 60))

    if not school_location:
        return jsonify({'error': 'School location missing'}), 400

    try:
        hours, minutes = map(int, school_time.split(':'))
        school_arrival_seconds = hours * 3600 + minutes * 60
    except:
        school_arrival_seconds = 27000

    try:
        recalculated = recalculate_manually_adjusted_routes(
            routes, school_location, API_KEY, school_arrival_seconds, max_ride_time,
            service_time=service_time
        )
        return jsonify({'success': True, 'routes': recalculated})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/fetch-geometry', methods=['POST'])
def fetch_geometry_endpoint():
    """Fetch real road geometry for a single route on-demand.

    Uses the local OSM graph (singapore_drive.graphml) via OSMnx — no OneMap
    call here, so this works even without ONEMAP_EMAIL/PASSWORD configured.
    """
    from route_optimizer import enrich_routes_with_geometry

    data = request.json
    route = data.get('route')
    school_time = data.get('school_time', '07:30')
    max_ride_time = int(data.get('max_ride_time', 60))
    service_time = int(data.get('service_time', 60))

    if not route:
        return jsonify({'error': 'Route data is required'}), 400

    # Parse school time
    time_parts = school_time.split(':')
    arrival_seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60

    try:
        # api_key arg is kept for signature compatibility but unused downstream.
        enriched_routes = enrich_routes_with_geometry(
            [route], None, arrival_seconds, max_ride_time,
            service_time=service_time
        )
        return jsonify({'route': enriched_routes[0]})
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error fetching geometry: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/road-types-geojson', methods=['GET'])
def road_types_geojson_endpoint():
    """Serve the Singapore drive network as GeoJSON, color-keyed by OSM
    `highway` tag. Used by the front-end overlay so the user can eyeball
    whether OSM tags match real road tier (and whether the
    SCHOOL_BUS_SPEED_KMH calibration is plausible).

    Builds once and caches to disk — the graph is static so subsequent
    calls just stream the file.
    """
    import json as _json
    from flask import send_file

    cache_path = os.path.join(os.path.dirname(__file__), 'sg_osm', 'road_types.geojson')

    if not os.path.exists(cache_path):
        from local_routing import get_graph
        from route_optimizer import edge_bus_speed_kmh, SCHOOL_BUS_SPEED_KMH

        g = get_graph()
        features = []
        skipped = 0
        for u, v, k, data in g.edges(keys=True, data=True):
            geom = data.get('geometry')
            highway = data.get('highway')
            if isinstance(highway, list):
                highway = highway[0] if highway else None
            highway_str = str(highway) if highway is not None else 'unknown'

            if geom is not None:
                try:
                    coords = [[lng, lat] for lng, lat in geom.coords]
                except Exception:
                    coords = None
            else:
                coords = None

            if not coords:
                # Fallback: straight line between the two nodes.
                try:
                    u_node = g.nodes[u]
                    v_node = g.nodes[v]
                    coords = [
                        [float(u_node['x']), float(u_node['y'])],
                        [float(v_node['x']), float(v_node['y'])],
                    ]
                except Exception:
                    skipped += 1
                    continue

            speed = edge_bus_speed_kmh(highway)
            in_table = highway_str in SCHOOL_BUS_SPEED_KMH
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'LineString', 'coordinates': coords},
                'properties': {
                    'highway': highway_str,
                    'speed_kmh': speed,
                    'in_table': in_table,
                },
            })

        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w') as f:
            _json.dump({'type': 'FeatureCollection', 'features': features}, f)
        print(f"[road_types] Built GeoJSON: {len(features)} features, {skipped} skipped → {cache_path}")

    response = send_file(cache_path, mimetype='application/json')
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


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

@app.route('/api/upload-students-csv', methods=['POST'])
def upload_students_csv_endpoint():
    """Handle custom CSV uploads"""
    global students
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file and file.filename.endswith('.csv'):
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        loaded_students = []
        
        start_id = len(students) + 1
        for idx, row in enumerate(reader, start=start_id):
            student_id = row.get('student_id', row.get('ID', str(idx)))
            name = row.get("Sender's first name", row.get('Name', row.get('name', row.get('student_name', ''))))
            address = row.get('Pick-up address line 1', '')
            address_2 = row.get('Pick-up address line 2', '')
            if address_2 and address_2 != 'Null':
                address = f"{address}, {address_2}"
            remark = row.get('remark', row.get('Remark', ''))
            latitude = row.get('latitude', row.get('Pick-up latitude', ''))
            longitude = row.get('longitude', row.get('Pick-up longitude', ''))
            
            if not latitude or not longitude:
                continue
            
            try:
                student = {
                    'id': idx,
                    'student_id': student_id,
                    'name': name,
                    'address': address,
                    'postal': '',
                    'address_note': remark,
                    'latitude': float(latitude),
                    'longitude': float(longitude),
                    'family_code': str(row.get('family_code', row.get('Family Code', ''))),
                    'special_needs': str(row.get('special_needs', row.get('Special Needs', ''))).lower() in ['true', 'yes', '1', 'y']
                }
                loaded_students.append(student)
            except ValueError:
                continue
                
        students.extend(loaded_students)
        return jsonify({
            'success': True,
            'loaded': len(loaded_students),
            'total_students': len(students)
        })
    return jsonify({'error': 'Invalid file format'}), 400


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


@app.route('/students')
def students_page():
    """Students management page"""
    return render_template('students.html')


@app.route('/settings')
def settings_page():
    """Settings page - set school location"""
    return render_template('settings.html')


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
            vehicle_id = route.get('vehicle_id', '')
            vehicle_plate = route.get('vehicle_plate', '')
            
            # User requested to show "ID" (e.g., VN11-01) instead of Plate Number
            if vehicle_id:
                route_name = vehicle_id
            elif vehicle_plate and vehicle_plate != 'Pending':
                route_name = vehicle_plate
            else:
                 route_name = route.get('bus_number', f"Bus {route_idx + 1}")
            
            # Use the students list directly from the route object
            # This is populated by route_optimizer and contains all metadata (ID, times, etc.)
            route_students = route.get('students', [])
            
            for s in route_students:
                export_data.append({
                    'route_name': route_name,
                    'vehicle_id': vehicle_id,
                    'vehicle_plate': vehicle_plate,
                    'student_id': s.get('student_id', s.get('id', 'Unknown')),
                    'student_name': s.get('name', 'Unknown'),
                    'pickup_time': s.get('pickup_time', '-'),
                    'latitude': s.get('latitude', ''),
                    'longitude': s.get('longitude', ''),
                    'postal_code': s.get('postal', '') or s.get('postal_code', ''),
                    'address': s.get('address', ''),
                    'address_note': s.get('address_note', '')
                })

        if format_type == 'json':
            return jsonify({'data': export_data})
        
        # CSV FORMAT
        output = io.StringIO()
        writer = csv.writer(output)
        # CSV FORMAT
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Bus', 'Vehicle ID', 'Plate Number', 'Student ID', 'Latitude', 'Longitude', 'Postal Code', 'Remark', 'Pickup Time', 'Student Name', 'Address'])
        
        for item in export_data:
             writer.writerow([
                 item['route_name'],
                 item['vehicle_id'],
                 item['vehicle_plate'],
                 item['student_id'],
                 item['latitude'],
                 item['longitude'],
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


# ============ AI Chat Endpoint ============

@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    """
    Natural-language route editor backed by Gemini.

    Body:
      {
        "message": "...",
        "routes":  [...current routes...],
        "history": [{role, text}, ...],   # optional, last ~10 turns
        "model":   "gemini-2.5-flash" | "gemini-2.5-pro",
        "school_time": "07:30",
        "max_ride_time": 60
      }
    """
    from chat_handler import run_chat, collect_warnings
    from route_optimizer import recalculate_manually_adjusted_routes

    data = request.json or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'message is required'}), 400

    incoming_routes = data.get('routes') or []
    history = data.get('history') or []
    model = data.get('model') or os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
    school_time = data.get('school_time', '07:30')
    max_ride_time = int(data.get('max_ride_time', 60))

    try:
        result = run_chat(message, incoming_routes, history, model_name=model)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Chat failed: {e}'}), 500

    if result.get('error'):
        return jsonify({'error': result['error']}), 500

    updated_routes = result.get('updated_routes', incoming_routes)

    # Recalculate times/distances if any mutation succeeded
    recalculated = updated_routes
    if result.get('needs_recalc') and school_location:
        try:
            hours, minutes = map(int, school_time.split(':'))
            school_arrival_seconds = hours * 3600 + minutes * 60
        except Exception:
            school_arrival_seconds = 27000

        try:
            recalculated = recalculate_manually_adjusted_routes(
                updated_routes, school_location, API_KEY,
                school_arrival_seconds, max_ride_time
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({
                'ai_message': result.get('ai_message'),
                'tool_calls': result.get('tool_calls'),
                'routes': updated_routes,
                'warnings': [f'Recalculation failed: {e}'],
                'clarification': result.get('clarification'),
            }), 200

    warnings = collect_warnings(recalculated, max_ride_time) if result.get('needs_recalc') else []

    return jsonify({
        'ai_message': result.get('ai_message'),
        'tool_calls': result.get('tool_calls'),
        'routes': recalculated,
        'warnings': warnings,
        'clarification': result.get('clarification'),
        'recalculated': bool(result.get('needs_recalc')),
    })


if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)



