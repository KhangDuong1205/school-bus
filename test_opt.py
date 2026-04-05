import requests
import json
import time

url = 'http://127.0.0.1:5000/api/optimise-routes'
payload = {
    'max_buses': 15,
    'school_time': '07:30',
    'max_ride_time': 60
}

start = time.time()
print("Starting optimization request (this should be fast now)...")
response = requests.post(url, json=payload)
end = time.time()

print(f"Request took {end-start:.2f} seconds")
print(f"Status Code: {response.status_code}")

try:
    data = response.json()
    if 'error' in data:
        print(f"ERROR returned: {data['error']}")
    else:
        print(f"Success! Generated {len(data.get('routes', []))} routes.")
        for i, r in enumerate(data.get('routes', [])):
            print(f"  Route {i+1}: {len(r.get('students', []))} students, {r.get('distance_km', 0)}km, {r.get('time_minutes', 0)}min")
            # Verify that geometry is NOT pre-fetched in segments
            has_geometry = False
            for seg in r.get('segments', []):
                if 'geometry' in seg and seg['geometry']:
                    has_geometry = True
            if has_geometry:
                print(f"  WARNING: Geometry was pre-fetched for Route {i+1}!")
except Exception as e:
    print(f"Failed to parse JSON: {e}")
