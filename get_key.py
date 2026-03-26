
import requests

base_url = "https://three.arcprize.org"

print("Fetching anonymous key...")
url_anon = f"{base_url}/api/games/anonkey"
try:
    resp_anon = requests.get(url_anon, headers={"Accept": "application/json"}, timeout=10)
    print(f"Anon status: {resp_anon.status_code}")
    if resp_anon.status_code == 200:
        data = resp_anon.json()
        anon_key = data.get("api_key")
        print(f"Got anon key: {anon_key}")
        
        # Write to a temp .env to test
        with open("test.env", "w") as f:
            f.write(f"ARC_API_KEY={anon_key}\n")
            f.write("OPERATION_MODE=online\n")
            f.write("ARC_BASE_URL=https://three.arcprize.org/\n")
            f.write("SCHEME=https\n")
            f.write("HOST=three.arcprize.org\n")
            f.write("PORT=443\n")
            
        print("Testing with new anon key...")
        headers = {"X-Api-Key": anon_key, "Accept": "application/json"}
        resp_test = requests.get(f"{base_url}/api/games", headers=headers, timeout=10)
        print(f"Games fetch status: {resp_test.status_code}")
        if resp_test.status_code == 200:
            print("SUCCESS! This key works.")
            # Overwrite the real .env if it works
            with open(".env", "r") as f:
                lines = f.readlines()
            with open(".env", "w") as f:
                for line in lines:
                    if line.startswith("ARC_API_KEY="):
                        f.write(f"ARC_API_KEY={anon_key}\n")
                    else:
                        f.write(line)
            print("Updated .env with working key.")
        else:
            print(f"Failed with anon key: {resp_test.text}")
    else:
        print(f"Failed to get anon key: {resp_anon.text}")
except Exception as e:
    print(f"Error: {e}")
