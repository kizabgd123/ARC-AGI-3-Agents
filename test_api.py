import os

import requests
from dotenv import load_dotenv

# Test with current .env
load_dotenv(".env")
key = os.getenv("ARC_API_KEY")
base_url = os.getenv("ARC_BASE_URL", "https://three.arcprize.org")

print(f"Testing with key: {key}")
url = f"{base_url}/api/games"
headers = {"X-Api-Key": key, "Accept": "application/json"}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print("Success with current key!")
    else:
        print(f"Error: {resp.text}")
except Exception as e:
    print(f"Request failed: {e}")

# Test anonymous
print("\nTesting anonymous...")
url_anon = f"{base_url}/api/games/anonkey"
try:
    resp_anon = requests.get(
        url_anon, headers={"Accept": "application/json"}, timeout=10
    )
    print(f"Anon status: {resp_anon.status_code}")
    if resp_anon.status_code == 200:
        anon_key = resp_anon.json().get("api_key")
        print(f"Got anon key: {anon_key}")

        # Test with anon key
        headers_anon = {"X-Api-Key": anon_key, "Accept": "application/json"}
        resp_test = requests.get(url, headers=headers_anon, timeout=10)
        print(f"Test with anon key status: {resp_test.status_code}")
except Exception as e:
    print(f"Anon request failed: {e}")
