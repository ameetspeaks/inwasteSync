import os
import requests
import json
import time
import argparse
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Configuration
SUPABASE_URL = os.getenv("VITE_SUPABASE_URL")
# Use Service Role Key for background tasks to bypass RLS
SUPABASE_KEY = os.getenv("VITE_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY")
GPS_API_BASE = "https://externalapi.autonautics.com.au/api"
GPS_USER = "jatin@inwaste.co"
GPS_PASS = "Jatin@213"

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error: Missing Supabase credentials in environment.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_gps_token():
    """Fetches GPS token from DB or refreshes from API."""
    try:
        # 1. Try DB first
        res = supabase.table("gps_integration_settings").select("*").eq("id", 1).execute()
        if res.data:
            data = res.data[0]
            expires_at = datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00'))
            if expires_at > datetime.now(expires_at.tzinfo) + timedelta(seconds=30):
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

def fetch_districts_and_vehicles():
    """Fetches all districts and their associated GPS vehicles."""
    vehicles = supabase.table("vehicles").select("id, gps_tracked_item_id, registration_number, village_id").eq("has_gps", True).execute()
    districs = supabase.table("districts").select("*").execute()
    blocks = supabase.table("blocks").select("*").execute()
    villages = supabase.table("villages").select("*").execute()
    
    # Build maps
    v_map = {v['id']: v for v in villages.data}
    b_map = {b['id']: b for b in blocks.data}
    d_map = {d['id']: d for d in districs.data}
    
    config_to_vehicles = {} # (uid, cid) -> [vehicle_records]
    
    for v in vehicles.data:
        village = v_map.get(v['village_id'])
        if not village: continue
        block = b_map.get(village['block_id'])
        if not block: continue
        district = d_map.get(block['district_id'])
        if not district: continue
        
        uid, cid = district.get('gps_user_id'), district.get('gps_client_id')
        if uid and cid:
            key = (uid, cid)
            if key not in config_to_vehicles:
                config_to_vehicles[key] = []
            config_to_vehicles[key].append(v)
            
    return config_to_vehicles

def sync_realtime(token):
    print(f"🚀 Starting Real-time GPS Sync at {datetime.now().isoformat()}")
    
    try:
        config_to_vehicles = fetch_districts_and_vehicles()
        if not config_to_vehicles:
            print("ℹ️ No active GPS configurations found.")
            return

        total_processed = 0
        for (uid, cid), vehicles in config_to_vehicles.items():
            print(f"📡 Syncing ClientID: {cid} (UserID: {uid}) with {len(vehicles)} vehicles...")
            url = f"{GPS_API_BASE}/Report/GetHealthCheckReport?UserID={uid}&ClientID={cid}"
            headers = {"Authorization": f"Bearer {token}"}
            
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("isSuccess") and data.get("data"):
                    items = data["data"]
                    print(f"✅ Received {len(items)} items from API.")
                    
                    # Create a lookup for vehicles in this district
                    v_lookup = {str(v['gps_tracked_item_id']): v for v in vehicles if v['gps_tracked_item_id']}
                    v_lookup_reg = {str(v['registration_number']): v for v in vehicles if v['registration_number']}
                    
                    for item in items:
                        tracked_id = str(item.get('trackedItemID') or item.get('TrackedItemID'))
                        item_name = str(item.get('itemName') or item.get('ItemName'))
                        
                        v = v_lookup.get(tracked_id) or v_lookup_reg.get(item_name)
                        
                        if v:
                            vid = v['id']
                            lat = float(item.get('lat') or item.get('Latitude', 0))
                            lon = float(item.get('long') or item.get('Longitude', 0))
                            speed = float(item.get('speed') or item.get('Speed', 0))
                            ignited = int(item.get('ignition') or item.get('Ignition', 0)) == 1
                            moving = int(item.get('movement') or item.get('Movement', 0)) == 1
                            ts = item.get('devicetimestamp') or item.get('deviceTimestamp') or item.get('DeviceTimestamp')
                            
                            # Update Vehicle
                            supabase.table("vehicles").update({
                                "last_gps_lat": lat,
                                "last_gps_long": lon,
                                "last_gps_speed": speed,
                                "is_ignited": ignited,
                                "is_moving": moving,
                                "last_gps_sync": datetime.now().isoformat(),
                            }).eq("id", vid).execute()
                            
                            # Insert Log
                            try:
                                supabase.table("gps_live_logs").insert({
                                    "vehicle_id": vid,
                                    "user_id": uid,
                                    "tracked_item_id": tracked_id,
                                    "device_timestamp": ts,
                                    "latitude": lat,
                                    "longitude": lon,
                                    "speed": speed,
                                    "ignition": 1 if ignited else 0,
                                    "movement": 1 if moving else 0,
                                    "raw_data": item
                                }).execute()
                                total_processed += 1
                            except Exception:
                                pass # Duplicate likely
                                
            else:
                print(f"❌ API Error {resp.status_code} for CID {cid}")

        print(f"🏁 Real-time sync completed. updates: {total_processed}")

    except Exception as e:
        print(f"❌ Critical error in realtime sync: {e}")

def backfill(token, date_str):
    print(f"🕰️ Starting Backfill for date: {date_str}")
    try:
        config_to_vehicles = fetch_districts_and_vehicles()
        if not config_to_vehicles:
            print("ℹ️ No active GPS configurations found.")
            return

        for (uid, cid), vehicles in config_to_vehicles.items():
            print(f"📡 Backfilling CID: {cid} on {date_str}...")
            start_dt = f"{date_str} 00:00:00"
            end_dt = f"{date_str} 23:59:59"
            
            tracked_ids = [str(v['gps_tracked_item_id']) for v in vehicles if v.get('gps_tracked_item_id')]
            if not tracked_ids: continue
            
            # Chunking
            chunk_size = 10
            for i in range(0, len(tracked_ids), chunk_size):
                chunk = tracked_ids[i:i+chunk_size]
                ids_str = ",".join(chunk)
                
                params = {
                    "UserID": uid,
                    "ClientID": cid,
                    "TrackedItemIDs": ids_str,
                    "StartDatetime": start_dt,
                    "EndDatetime": end_dt
                }
                
                headers = {"Authorization": f"Bearer {token}"}
                
                # Debug URL
                if i == 0:
                    print(f"🔗 Requesting: {GPS_API_BASE}/Report/GetTrackedPointReport")
                    print(f"📦 Params: {params}")

                resp = requests.get(f"{GPS_API_BASE}/Report/GetTrackedPointReport", headers=headers, params=params, timeout=60)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("isSuccess") and data.get("data"):
                        points = data["data"]
                        print(f"✅ Received {len(points)} historical points for chunk.")
                        
                        v_lookup = {str(v['gps_tracked_item_id']): v for v in vehicles}
                        
                        for p in points:
                            tid = str(p.get('trackedItemID'))
                            v = v_lookup.get(tid)
                            if v:
                                try:
                                    # Convert deviceTimestamp to ISO if needed, or rely on DB parsing
                                    # Usually '2026-04-10 12:34:56' is fine for Postgres timestamp
                                    supabase.table("gps_live_logs").insert({
                                        "vehicle_id": v['id'],
                                        "user_id": uid,
                                        "tracked_item_id": tid,
                                        "device_timestamp": p.get('deviceTimestamp'),
                                        "latitude": p.get('lat'),
                                        "longitude": p.get('long'),
                                        "speed": p.get('speed'),
                                        "ignition": p.get('ignition'),
                                        "movement": p.get('movement'),
                                        "raw_data": p
                                    }).execute()
                                except Exception:
                                    pass
                    else:
                        print(f"⚠️ API Info: {data.get('message', 'No data returned')}")
                else:
                    print(f"❌ Backfill API Error {resp.status_code} for CID {cid}")
                    if resp.text: print(f"📄 Response: {resp.text[:200]}")
                    
    except Exception as e:
        print(f"❌ Error in backfill: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPS Sync Engine")
    parser.add_argument("--backfill", type=str, help="Date to backfill (YYYY-MM-DD)")
    parser.add_argument("--loop", action="store_true", help="Run in a continuous loop")
    parser.add_argument("--interval", type=int, default=300, help="Loop interval in seconds")
    
    args = parser.parse_args()
    
    # For local testing, ensure you have env vars or use a .env file
    token = get_gps_token()
    if not token:
        print("❌ Could not obtain token. Exiting.")
        exit(1)
        
    if args.backfill:
        backfill(token, args.backfill)
    elif args.loop:
        while True:
            token = get_gps_token()
            sync_realtime(token)
            print(f"😴 Sleeping for {args.interval}s...")
            time.sleep(args.interval)
    else:
        sync_realtime(token)
