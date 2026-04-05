import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_CACHE_FILE = '.onemap_token'

def get_onemap_token():
    """
    Get OneMap API token. 
    Tries to read from cache first. If not found or expired, fetches a new one.
    """
    # 1. Try to read from cache
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, 'r') as f:
                data = json.load(f)
                token = data.get('access_token')
                expiry = int(data.get('expiry_timestamp', 0))
                
                # Check if token is still valid (with 1 hour buffer)
                if token and expiry > time.time() + 3600:
                    return token
        except (json.JSONDecodeError, ValueError, IOError):
            pass

    # 2. Fetch new token
    email = os.environ.get('ONEMAP_EMAIL')
    password = os.environ.get('ONEMAP_PASSWORD')
    
    # Fallback to existing API key if email/pass not provided
    if not email or not password:
        token = os.environ.get('ONEMAP_API_KEY')
        if token:
            return token
        raise ValueError("ONEMAP_EMAIL and ONEMAP_PASSWORD or ONEMAP_API_KEY must be set in environment")

    url = "https://www.onemap.gov.sg/api/auth/post/getToken"
    payload = {
        "email": email,
        "password": password
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        token = data.get('access_token')
        if not token:
            raise ValueError(f"No access_token in OneMap response: {data}")
            
        # 3. Save to cache
        with open(TOKEN_CACHE_FILE, 'w') as f:
            json.dump(data, f)
            
        return token
    except requests.exceptions.RequestException as e:
        # If request fails but we have an old token, maybe try it as a last resort?
        # For now, just raise the error.
        print(f"Error fetching OneMap token: {e}")
        # Last ditch: try ONEMAP_API_KEY
        token = os.environ.get('ONEMAP_API_KEY')
        if token:
            return token
        raise

if __name__ == "__main__":
    # Test
    try:
        t = get_onemap_token()
        print(f"Token: {t[:10]}...")
    except Exception as e:
        print(f"Failed: {e}")
