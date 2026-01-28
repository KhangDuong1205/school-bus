from flask import Flask, render_template, request, jsonify
import requests
from typing import List, Dict, Tuple
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

app = Flask(__name__)

@dataclass
class RouteSegment:
    from_lat: float
    from_lng: float
    to_lat: float
    to_lng: float
    distance: float
    duration: float  # in seconds

API_KEY = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxMTA3MywiZm9yZXZlciI6ZmFsc2UsImlzcyI6Ik9uZU1hcCIsImlhdCI6MTc2OTU5NzEzNSwibmJmIjoxNzY5NTk3MTM1LCJleHAiOjE3Njk4NTYzMzUsImp0aSI6IjBlNTI4YTY3LTJmOWMtNDZlNy04NzYyLTE1ZDllNGY4NjNlMSJ9.1w10JcYcvifND4R5aM7Aglq6sY1sgyNyOrb7xLBlfIZsD3kU3AZmDKmL9kxTvZceiZHwohZJHbrQOslVYbYJQFZ_1l40XcRJi58Ko9yDd7uPFojdX7AgSbTln12etii91pObauwJyYGdHBPI_wrQ5D2pyzpMxnOpQ0G73u8iiGxdTTr5Gxs8oUp0OGSEL63pjP6icdW6EaQEKgm3eV2ylPTp1Yx47Pz9bTS_xSRSFM6lzQKRVW7cnBKqUObaB8gl2Hydypy6EkBKpBkoHGRIureX5kMmlCpbizSnU_FTi3OAFRiQ2nfjOKYRUSHxKy0e6lB3rWfpL7fkNYL90b0o9A'

# In-memory storage (will use database later)
students = []
school_location = None
optimized_routes = []

# Constants
MAX_STUDENTS_PER_BUS = 40
AVERAGE_PICKUP_TIME = 60  # seconds per student pickup

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

@app.route('/api/school', methods=['POST'])
def set_school():
    """Set school location"""
    global school_location
    data = request.json
    
    school_location = {
        'name': data['name'],
        'address': data['address'],
        'postal': data['postal'],
        'latitude': float(data['latitude']),
        'longitude': float(data['longitude'])
    }
    
    return jsonify(school_location), 201

@app.route('/api/school', methods=['DELETE'])
def delete_school():
    """Delete school location"""
    global school_location
    school_location = None
    return jsonify({'success': True})


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


@app.route('/api/optimise-routes', methods=['POST'])
def optimise_routes_endpoint():
    """Optimise bus routes"""
    from route_optimizer import optimize_routes
    
    data = request.json
    max_buses = data.get('max_buses', 3)
    
    print(f"\n=== Optimise Routes Request ===")
    print(f"Max buses: {max_buses}")
    print(f"School location: {school_location is not None}")
    print(f"Number of students: {len(students)}")
    
    if not school_location:
        print("ERROR: No school location set")
        return jsonify({'error': 'Please set school location first'}), 400
    
    if not students or len(students) == 0:
        print("ERROR: No students added")
        return jsonify({'error': 'Please add students first'}), 400
    
    result = optimize_routes(school_location, students, max_buses, API_KEY)
    
    return jsonify(result)


@app.route('/api/generate-students', methods=['POST'])
def generate_students():
    """Generate random students with realistic clustering in neighborhoods"""
    data = request.json
    count = data.get('count', 10)
    num_clusters = data.get('clusters', 2)
    num_isolated = data.get('isolated', 0)  # Number of isolated students to generate
    
    num_clusters = max(1, min(5, num_clusters))
    
    # Define neighborhood clusters with MORE variety
    neighborhood_clusters = [
        ('Tampines', [
            ('Tampines Street', list(range(11, 95, 1))),  # Every block
            ('Tampines Avenue', list(range(1, 12))),
        ], 3),
        
        ('Jurong West', [
            ('Jurong West Street', list(range(11, 95, 1))),
            ('Jurong West Avenue', list(range(1, 10))),
        ], 3),
        
        ('Bedok', [
            ('Bedok North Avenue', list(range(100, 700, 5))),
            ('Bedok South Avenue', list(range(1, 5))),
            ('Bedok North Street', list(range(1, 50))),
        ], 2),
        
        ('Hougang', [
            ('Hougang Avenue', list(range(1, 12))),
            ('Hougang Street', list(range(11, 95, 1))),
        ], 2),
        
        ('Ang Mo Kio', [
            ('Ang Mo Kio Avenue', list(range(100, 800, 10))),
            ('Ang Mo Kio Street', list(range(11, 90, 1))),
        ], 2),
        
        ('Yishun', [
            ('Yishun Avenue', list(range(1, 12))),
            ('Yishun Street', list(range(11, 90, 1))),
            ('Yishun Ring Road', list(range(1, 100, 3))),
        ], 2),
        
        ('Sengkang', [
            ('Sengkang East Avenue', list(range(1, 10))),
            ('Sengkang West Avenue', list(range(1, 10))),
            ('Sengkang East Way', list(range(1, 20))),
            ('Sengkang Central', list(range(1, 100, 3))),
        ], 2),
        
        ('Punggol', [
            ('Punggol Drive', list(range(600, 700, 3))),
            ('Punggol Field', list(range(100, 200, 3))),
            ('Punggol Way', list(range(1, 50, 2))),
        ], 2),
        
        ('Woodlands', [
            ('Woodlands Avenue', list(range(1, 12))),
            ('Woodlands Street', list(range(11, 90, 1))),
            ('Woodlands Drive', list(range(1, 80, 2))),
        ], 1),
        
        ('Clementi', [
            ('Clementi Avenue', list(range(1, 10))),
            ('Clementi Street', list(range(11, 20))),
            ('Clementi West Street', list(range(1, 15))),
        ], 1),
    ]
    
    first_names = ['Wei', 'Hui', 'Ming', 'Jia', 'Xin', 'Yi', 'Zhi', 'Kai', 'Jun', 'Ling',
                   'Raj', 'Kumar', 'Priya', 'Arun', 'Siti', 'Ahmad', 'Nurul', 'Farah',
                   'David', 'Sarah', 'Daniel', 'Emily', 'Ryan', 'Sophie', 'Ethan', 'Chloe',
                   'Alex', 'Ben', 'Chris', 'Diana', 'Fiona', 'Grace', 'Henry', 'Iris']
    last_names = ['Tan', 'Lim', 'Lee', 'Ng', 'Ong', 'Wong', 'Goh', 'Chua', 'Chan', 'Koh',
                  'Kumar', 'Singh', 'Rahman', 'Abdullah', 'Ismail', 'Hassan',
                  'Smith', 'Johnson', 'Brown', 'Wilson', 'Chen', 'Liu', 'Zhang']
    
    weights = [cluster[2] for cluster in neighborhood_clusters]
    selected_neighborhoods = random.choices(neighborhood_clusters, weights=weights, k=num_clusters)
    
    # Distribute students
    students_per_neighborhood = []
    remaining = count
    
    for i in range(num_clusters):
        if i == num_clusters - 1:
            students_per_neighborhood.append(remaining)
        else:
            if num_clusters == 1:
                allocation = remaining
            else:
                min_allocation = max(1, int(remaining * 0.2))
                max_allocation = int(remaining * 0.6)
                allocation = random.randint(min_allocation, max_allocation)
            
            students_per_neighborhood.append(allocation)
            remaining -= allocation
    
    generated_students = []
    url = 'https://www.onemap.gov.sg/api/common/elastic/search'
    headers = {'Authorization': API_KEY}
    
    neighborhoods_used = []
    
    for neighborhood_idx, (area_name, road_patterns, _) in enumerate(selected_neighborhoods):
        target_count = students_per_neighborhood[neighborhood_idx]
        
        print(f"Generating {target_count} students in {area_name}...")
        neighborhoods_used.append(area_name)
        
        # Build address pool - allow duplicates after 70% unique
        address_pool = []
        used_addresses = set()
        attempts = 0
        max_attempts = target_count * 3  # Reasonable limit
        
        while len(address_pool) < target_count and attempts < max_attempts:
            attempts += 1
            
            road_name, block_list = random.choice(road_patterns)
            block_num = random.choice(block_list)
            search_val = f"{block_num} {road_name}"
            
            try:
                params = {
                    'searchVal': search_val,
                    'returnGeom': 'Y',
                    'getAddrDetails': 'Y',
                    'pageNum': 1
                }
                
                response = requests.get(url, params=params, headers=headers, timeout=5)
                result = response.json()
                
                if result.get('found', 0) > 0:
                    residential_results = [
                        r for r in result['results']
                        if any(keyword in r['ADDRESS'].upper() for keyword in 
                               ['BLK', 'BLOCK', 'AVENUE', 'STREET', 'ROAD', 'DRIVE', 'LORONG'])
                        and not any(keyword in r['ADDRESS'].upper() for keyword in
                               ['MALL', 'CENTRE', 'CENTER', 'MARKET', 'HAWKER', 'SCHOOL', 
                                'HOSPITAL', 'CLINIC', 'LIBRARY', 'COMMUNITY', 'PARK'])
                    ]
                    
                    for addr in residential_results[:3]:
                        # Allow duplicates after we have 70% unique addresses
                        if addr['ADDRESS'] not in used_addresses or len(address_pool) > target_count * 0.7:
                            address_pool.append(addr)
                            used_addresses.add(addr['ADDRESS'])
                            
                            if len(address_pool) >= target_count:
                                break
                    
            except Exception as e:
                continue
        
        print(f"  Found {len(address_pool)} addresses for {area_name}")
        
        # Generate students from pool
        for i in range(min(target_count, len(address_pool))):
            address_data = address_pool[i]
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
            
            student = {
                'id': len(students) + len(generated_students) + 1,
                'name': name,
                'address': address_data['ADDRESS'],
                'postal': address_data['POSTAL'],
                'latitude': float(address_data['LATITUDE']),
                'longitude': float(address_data['LONGITUDE'])
            }
            
            generated_students.append(student)
        
        print(f"  Generated {len(generated_students) - sum([len([s for s in generated_students if neighborhoods_used.index(area_name) < neighborhoods_used.index(n)]) for n in neighborhoods_used[:neighborhood_idx]])} students in {area_name}")
    
    # Generate isolated students (5km+ away from clusters)
    isolated_generated = 0
    if num_isolated > 0:
        print(f"\nGenerating {num_isolated} isolated students (5km+ from clusters)...")
        
        # Define distant areas (far from typical clusters)
        distant_areas = [
            ('Sentosa', [('Sentosa Gateway', list(range(1, 10)))]),
            ('Changi', [('Changi Village Road', list(range(1, 50, 5)))]),
            ('Tuas', [('Tuas South Avenue', list(range(1, 20)))]),
            ('Lim Chu Kang', [('Lim Chu Kang Road', list(range(1, 100, 10)))]),
            ('Pasir Ris', [('Pasir Ris Drive', list(range(1, 20)))]),
        ]
        
        for i in range(num_isolated):
            attempts = 0
            max_attempts = 20
            
            while attempts < max_attempts:
                attempts += 1
                
                # Pick random distant area
                area_name, road_patterns = random.choice(distant_areas)
                road_name, block_list = random.choice(road_patterns)
                block_num = random.choice(block_list)
                search_val = f"{block_num} {road_name}"
                
                try:
                    params = {
                        'searchVal': search_val,
                        'returnGeom': 'Y',
                        'getAddrDetails': 'Y',
                        'pageNum': 1
                    }
                    
                    response = requests.get(url, params=params, headers=headers, timeout=5)
                    result = response.json()
                    
                    if result.get('found', 0) > 0:
                        address_data = result['results'][0]
                        name = f"{random.choice(first_names)} {random.choice(last_names)}"
                        
                        student = {
                            'id': len(students) + len(generated_students) + 1,
                            'name': name,
                            'address': address_data['ADDRESS'],
                            'postal': address_data['POSTAL'],
                            'latitude': float(address_data['LATITUDE']),
                            'longitude': float(address_data['LONGITUDE'])
                        }
                        
                        generated_students.append(student)
                        isolated_generated += 1
                        print(f"  Generated isolated student: {name} at {area_name}")
                        break
                        
                except Exception as e:
                    continue
    
    students.extend(generated_students)
    
    return jsonify({
        'success': True,
        'generated': len(generated_students),
        'isolated_generated': isolated_generated,
        'requested': count,
        'neighborhoods_used': len(neighborhoods_used),
        'neighborhoods': neighborhoods_used
    })

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
