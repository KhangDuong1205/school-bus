import requests

url = 'http://127.0.0.1:5000/api/school'
payload = {
    'name': 'Test School',
    'address': '10 Test Road',
    'latitude': 1.3521,
    'longitude': 103.8198
}

response = requests.put(url, json=payload)
print("School set:", response.status_code)
