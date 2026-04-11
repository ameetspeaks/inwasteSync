import os
import json
import glob
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("VITE_SUPABASE_URL")
key = os.environ.get("VITE_SUPABASE_SERVICE_ROLE_KEY")

if not key:
    print("❌ VITE_SUPABASE_SERVICE_ROLE_KEY not found. Ensure it is set in GitHub Secrets.")
    exit(1)

supabase: Client = create_client(url, key)

# Data folder is expected to be inside the inwastesync directory
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
            "ignition": p["ignition"] == 1,
            "movement": p["movement"] == 1,
            "raw_data": p
        })

    # Upsert in chunks
    chunk_size = 500
    for i in range(0, len(logs), chunk_size):
        chunk = logs[i:i + chunk_size]
        supabase.table("gps_live_logs").upsert(chunk, on_conflict="vehicle_id,device_timestamp").execute()
        
    print(f"✅ Ingested {len(logs)} points.")

    # Create historical session for the day
    date_str = points[0]["deviceTimestamp"].split("T")[0]
    start_time = f"{date_str}T00:00:00+05:30"
    end_time = f"{date_str}T23:59:59+05:30"
    
    existing = supabase.table("tracking_sessions").select("id") \
        .eq("vehicle_id", VEHICLE_ID) \
        .gte("start_time", start_time) \
        .lte("start_time", end_time).execute()
        
    if not existing.data:
        supabase.table("tracking_sessions").insert({
            "vehicle_id": VEHICLE_ID,
            "status": "completed",
            "start_time": start_time,
            "end_time": end_time,
            "total_distance_km": 0,
            "points_visited": 0
        }).execute()
        print(f"✨ Created historical session for {date_str}")
    else:
        print(f"ℹ️ Session already exists for {date_str}")

if __name__ == "__main__":
    if not os.path.exists(DATA_DIR):
        print(f"❌ Data directory not found at: {DATA_DIR}")
        exit(1)
        
    files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    files.sort()
    for f in files:
        ingest_file(f)
    print("\n🏁 All historical data mapped successfully.")
