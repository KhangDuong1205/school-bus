import urllib.request
import json
import time

# 1. Set School
req1 = urllib.request.Request('http://127.0.0.1:5000/api/school', 
    data=json.dumps({'name':'School', 'latitude':1.35, 'longitude':103.8}).encode(), 
    headers={'Content-Type': 'application/json'}, method='PUT')
urllib.request.urlopen(req1)
print("School set")

# 2. Load Students
req2 = urllib.request.Request('http://127.0.0.1:5000/api/load-students-csv', method='POST')
resp2 = urllib.request.urlopen(req2)
print("Students loaded:", json.loads(resp2.read()))

# 3. Optimize
req3 = urllib.request.Request('http://127.0.0.1:5000/api/optimise-routes', 
    data=json.dumps({'max_buses': 15, 'school_time': '07:30', 'max_ride_time': 60}).encode(), 
    headers={'Content-Type': 'application/json'}, method='POST')
start = time.time()
resp3 = urllib.request.urlopen(req3)
data = json.loads(resp3.read())
end = time.time()

routes = data.get("routes", [])
total_mapped = sum(r.get("student_count", 0) for r in routes)
print(f"Optimization took {end-start:.2f}s")
print(f"Success! Generated {len(routes)} routes.")
print(f"Total students mapped: {total_mapped} / 311")
if "error" in data:
    print("Error:", data["error"])
