import os
import json
import glob
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("VITE_SUPABASE_URL")
key = os.environ.get("VITE_SUPABASE_SERVICE_ROLE_KEY")

if not key:
    print("❌ VITE_SUPABASE_SERVICE_ROLE_KEY not found.")
    exit(1)

supabase: Client = create_client(url, key)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "data")
VEHICLE_ID = "9166929d-3617-4e8e-80af-aaea16bbdc54" # UP32-MUS-0105

def ingest_file(file_path):
    print(f"\n📂 Processing {os.path.basename(file_path)}...")
    with open(file_path, "r") as f:
        data = json.load(f)
    
    if not data.get("isSuccess") or not data.get("data"):
        return
        
    points = data["data"]
    tracked_item_id = str(points[0]["trackedItemID"])
    date_str = points[0]["deviceTimestamp"].split("T")[0]
    
    start_time = f"{date_str}T00:00:00+05:30"
    end_time = f"{date_str}T23:59:59+05:30"

    # 1. FIND ACTUAL ROUTE & ASSIGNED DRIVER
    # Get vehicle details including assigned driver
    v_res = supabase.table("vehicles").select("id, assigned_driver_id").eq("id", VEHICLE_ID).single().execute()
    if not v_res.data:
        print(f"❌ Vehicle {VEHICLE_ID} not found.")
        return
    
    driver_id = v_res.data.get("assigned_driver_id")
    
    # Find route assigned to this vehicle
    r_res = supabase.table("routes").select("id").eq("vehicle_id", VEHICLE_ID).limit(1).execute()
    if not r_res.data:
        print(f"❌ No route found for vehicle {VEHICLE_ID}. Cannot create session.")
        return
    route_id = r_res.data[0]["id"]

    # If no driver assigned, try to find a previous driver session for this vehicle
    if not driver_id:
        print(f"⚠️ No driver assigned to vehicle. Looking for last active driver...")
        prev_s = supabase.table("tracking_sessions").select("driver_id").eq("vehicle_id", VEHICLE_ID).limit(1).execute()
        if prev_s.data:
            driver_id = prev_s.data[0]["driver_id"]
            print(f"✅ Found previous driver: {driver_id}")
        else:
            # Absolute fallback to first driver in system if still null (to prevent crash)
            d_fallback = supabase.table("profiles").select("id").eq("role", "driver").limit(1).execute()
            if d_fallback.data:
                driver_id = d_fallback.data[0]["id"]
                print(f"ℹ️ Using system fallback driver: {driver_id}")

    if not driver_id:
        print("❌ No driver could be determined. Violates database constraint.")
        return

    # 2. CLEAN UP OLD DATA
    supabase.table("gps_live_logs").delete() \
        .eq("vehicle_id", VEHICLE_ID) \
        .gte("device_timestamp", start_time) \
        .lte("device_timestamp", end_time).execute()
    
    supabase.table("tracking_sessions").delete() \
        .eq("vehicle_id", VEHICLE_ID) \
        .gte("start_time", start_time) \
        .lte("start_time", end_time).execute()

    # 3. CONVERT POINTS
    logs = []
    for p in points:
        ts = p["deviceTimestamp"]
        if "+" not in ts:
            ts = f"{ts}+05:30"
            
        logs.append({
            "vehicle_id": VEHICLE_ID,
            "tracked_item_id": tracked_item_id,
            "device_timestamp": ts,
            "latitude": p["lat"],
            "longitude": p["long"],
            "speed": p["speed"],
            "ignition": 1 if p["ignition"] == 1 else 0,
            "movement": 1 if p["movement"] == 1 else 0,
            "raw_data": p
        })

    # 4. INSERT LOGS
    chunk_size = 500
    for i in range(0, len(logs), chunk_size):
        chunk = logs[i:i + chunk_size]
        supabase.table("gps_live_logs").insert(chunk).execute()
        
    print(f"✅ Ingested {len(logs)} points.")

    # 5. CREATE SESSION
    supabase.table("tracking_sessions").insert({
        "vehicle_id": VEHICLE_ID,
        "route_id": route_id,
        "driver_id": driver_id,
        "status": "completed",
        "start_time": start_time,
        "end_time": end_time,
        "total_distance_km": 0,
        "points_visited": 0
    }).execute()
    print(f"✨ Created historical session for {date_str} with assigned driver.")

if __name__ == "__main__":
    if not os.path.exists(DATA_DIR):
        print(f"❌ Data directory not found: {DATA_DIR}")
        exit(1)
        
    files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    files.sort()
    for f in files:
        ingest_file(f)
    print("\n🏁 Historical data rewrite complete.")
