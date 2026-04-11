import requests
import json
from gps_config import GPS_API_BASE, supabase
from gps_engine import fetch_districts_and_vehicles

def backfill(token, date_str):
    print(f"🕰️ Starting Backfill for date: {date_str}")
    try:
        config_to_vehicles = fetch_districts_and_vehicles()
        if not config_to_vehicles:
            print("ℹ️ No active GPS configurations found.")
            return

        for (uid, cid), vehicles in config_to_vehicles.items():
            print(f"📡 Backfilling CID: {cid} on {date_str}...")
            start_dt = f"{date_str}T00:00:00"
            end_dt = f"{date_str}T23:59:59"
            
            tracked_ids = [str(v['gps_tracked_item_id']) for v in vehicles if v.get('gps_tracked_item_id')]
            if not tracked_ids: continue
            
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
                        v_lookup = {str(v['gps_tracked_item_id']): v for v in vehicles}
                        
                        for p in points:
                            tid = str(p.get('trackedItemID'))
                            v = v_lookup.get(tid)
                            if v:
                                try:
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
                    print(f"❌ Backfill API Error {resp.status_code}")
    except Exception as e:
        print(f"❌ Error in backfill: {e}")
