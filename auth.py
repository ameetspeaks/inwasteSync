import requests
from datetime import datetime, timedelta
from config import supabase, GPS_API_BASE, GPS_USER, GPS_PASS
from utils import parse_iso

def get_gps_token():
    """Fetches GPS token from DB or refreshes from API."""
    try:
        # 1. Try DB first
        res = supabase.table("gps_integration_settings").select("*").eq("id", 1).execute()
        if res.data:
            data = res.data[0]
            expires_at = parse_iso(data['expires_at'])
            if expires_at and expires_at > datetime.now(expires_at.tzinfo) + timedelta(seconds=30):
                return data['token']

        # 2. Refresh from API
        print("🔄 Refreshing GPS API Token...")
        url = f"{GPS_API_BASE}/Auth/login"
        payload = {"userName": GPS_USER, "password": GPS_PASS}
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("isSuccess"):
                token = data["data"]["tokenKey"]
                # Store back to DB
                expires = (datetime.now() + timedelta(minutes=14)).isoformat()
                supabase.table("gps_integration_settings").upsert({
                    "id": 1,
                    "token": token,
                    "expires_at": expires
                }).execute()
                print("✅ Token refreshed and stored.")
                return token
            else:
                print(f"❌ GPS Login failed: {data.get('message')}")
        else:
            print(f"❌ GPS Login HTTP Error: {resp.status_code}")
    except Exception as e:
        print(f"❌ Error getting GPS token: {e}")
    return None
