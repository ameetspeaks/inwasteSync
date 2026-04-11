import requests
import json
from datetime import datetime, timedelta
from gps_config import supabase, GPS_API_BASE
from gps_utils import parse_iso
from gps_engine import fetch_districts_and_vehicles, process_gps_points

def sync_realtime(token):
    now = datetime.now()
    start_dt = (now - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S")
    end_dt = now.strftime("%Y-%m-%dT%H:%M:%S")
    
    print(f"🚀 Starting Incremental GPS Sync at {now.isoformat()}")
    
    try:
        config_to_vehicles = fetch_districts_and_vehicles()
        if not config_to_vehicles:
            print("ℹ️ No active GPS configurations found.")
            return

        total_processed = 0
        for (uid, cid), vehicles in config_to_vehicles.items():
            to_sync = []
            now_utc = datetime.now()
            
            for v in vehicles:
                off_count = v.get('ignition_off_count', 0)
                last_sync_str = v.get('last_gps_sync')
                
                if off_count >= 3 and last_sync_str:
                    last_sync = parse_iso(last_sync_str)
                    if now_utc.tzinfo is None:
                        now_comp = now_utc.replace(tzinfo=last_sync.tzinfo)
                    else:
                        now_comp = now_utc

                    if now_comp < last_sync + timedelta(minutes=14):
                        continue
                to_sync.append(v)

            if not to_sync: continue

            tracked_ids = [str(v['gps_tracked_item_id']) for v in to_sync if v.get('gps_tracked_item_id')]
            if not tracked_ids: continue
            
            print(f"📡 Syncing CID: {cid} ({len(tracked_ids)}/{len(vehicles)} vehicles)...")
            
            # Find active sessions
            v_to_session = {}
            active_sessions = supabase.table("tracking_sessions").select("id, vehicle_id").eq("status", "in_progress").execute()
            for s in active_sessions.data:
                v_to_session[s['vehicle_id']] = s['id']
            
            chunk_size = 10
            for i in range(0, len(tracked_ids), chunk_size):
                chunk = tracked_ids[i:i+chunk_size]
                params = {
                    "UserID": uid,
                    "ClientID": cid,
                    "TrackedItemIDs": ",".join(chunk),
                    "StartDatetime": start_dt,
                    "EndDatetime": end_dt
                }
                headers = {"Authorization": f"Bearer {token}"}
                resp = requests.get(f"{GPS_API_BASE}/Report/GetTrackedPointReport", headers=headers, params=params, timeout=60)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("isSuccess") and data.get("data"):
                        points = data["data"]
                        v_lookup = {str(v['gps_tracked_item_id']): v for v in to_sync}
                        total_processed += process_gps_points(points, v_lookup, uid, v_to_session)
                        
        print(f"🏁 Incremental sync completed. logs processed: {total_processed}")
    except Exception as e:
        print(f"❌ Critical error in sync: {e}")
