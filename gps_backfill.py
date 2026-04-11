import requests
import json
from datetime import datetime, timedelta
from gps_config import GPS_API_BASE, supabase
from gps_engine import fetch_districts_and_vehicles
from gps_utils import ensure_ist

def backfill_range(token, start_date_str, end_date_str):
    """Backfills data for a range of dates, one day at a time."""
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        backfill(token, date_str)
        current_date += timedelta(days=1)

def backfill(token, date_str):
    print(f"\n🕰️ Starting Backfill for date: {date_str}")
    try:
        config_to_vehicles = fetch_districts_and_vehicles()
        if not config_to_vehicles:
            print("ℹ️ No active GPS configurations found.")
            return

        # Prepare date boundaries
        start_time = f"{date_str}T00:00:00+05:30"
        end_time = f"{date_str}T23:59:59+05:30"

        for (uid, cid), vehicles in config_to_vehicles.items():
            print(f"📡 Processing Group CID: {cid} for {date_str}...")
            
            # 1. Fetch data for this group
            tracked_ids = [str(v['gps_tracked_item_id']) for v in vehicles if v.get('gps_tracked_item_id')]
            if not tracked_ids: continue
            
            all_points = []
            chunk_size = 10
            for i in range(0, len(tracked_ids), chunk_size):
                chunk = tracked_ids[i:i+chunk_size]
                params = {
                    "UserID": uid,
                    "ClientID": cid,
                    "TrackedItemIDs": ",".join(chunk),
                    "StartDatetime": f"{date_str}T00:00:00",
                    "EndDatetime": f"{date_str}T23:59:59"
                }
                headers = {"Authorization": f"Bearer {token}"}
                resp = requests.get(f"{GPS_API_BASE}/Report/GetTrackedPointReport", headers=headers, params=params, timeout=60)
                
                if resp.status_code == 200:
                    api_data = resp.json()
                    if api_data.get("isSuccess") and api_data.get("data"):
                        all_points.extend(api_data["data"])
                else:
                    print(f"❌ API Error {resp.status_code} for chunk {i}")

            if not all_points:
                print(f"ℹ️ No data found for group {cid} on {date_str}.")
                continue

            # 2. Process points per vehicle
            v_lookup = {str(v['gps_tracked_item_id']): v for v in vehicles}
            vehicle_points = {}
            for p in all_points:
                tid = str(p.get('trackedItemID'))
                if tid not in vehicle_points:
                    vehicle_points[tid] = []
                vehicle_points[tid].append(p)

            for tid, points in vehicle_points.items():
                v = v_lookup.get(tid)
                if not v: continue
                
                v_id = v['id']
                print(f"🚜 Mapping vehicle {v['registration_number']} ({len(points)} points)...")

                try:
                    # OVERWRITE: Clean up existing data for the day
                    # Delete Logs
                    supabase.table("gps_live_logs").delete() \
                        .eq("vehicle_id", v_id) \
                        .gte("device_timestamp", start_time) \
                        .lte("device_timestamp", end_time).execute()
                    
                    # Delete Sessions
                    supabase.table("tracking_sessions").delete() \
                        .eq("vehicle_id", v_id) \
                        .gte("start_time", start_time) \
                        .lte("start_time", end_time).execute()

                    # 3. INSERT LOGS
                    logs_to_insert = []
                    for p in points:
                        ts = ensure_ist(p.get('deviceTimestamp'))
                        
                        logs_to_insert.append({
                            "vehicle_id": v_id,
                            "user_id": uid,
                            "tracked_item_id": tid,
                            "device_timestamp": ts,
                            "latitude": p.get('lat'),
                            "longitude": p.get('long'),
                            "speed": p.get('speed'),
                            "ignition": p.get('ignition'),
                            "movement": p.get('movement'),
                            "raw_data": p
                        })

                    # Batch insert logs
                    chunk_size_logs = 500
                    for i in range(0, len(logs_to_insert), chunk_size_logs):
                        supabase.table("gps_live_logs").insert(logs_to_insert[i:i+chunk_size_logs]).execute()

                    # 4. CREATE HISTORICAL SESSION
                    # Find route and driver for mapping
                    route_id = v.get('route_id')
                    driver_id = v.get('driver_id')
                    
                    if not route_id:
                        r_res = supabase.table("routes").select("id, assigned_driver_id").eq("vehicle_id", v_id).limit(1).execute()
                        if r_res.data:
                            route_id = r_res.data[0]["id"]
                            driver_id = r_res.data[0].get("assigned_driver_id")

                    if route_id and driver_id:
                        # Determine actual start/end from logs if possible
                        sorted_points = sorted(points, key=lambda x: x.get('deviceTimestamp', ''))
                        actual_start = sorted_points[0].get('deviceTimestamp')
                        actual_end = sorted_points[-1].get('deviceTimestamp')
                        
                        if actual_start: actual_start = ensure_ist(actual_start)
                        if actual_end: actual_end = ensure_ist(actual_end)

                        session_resp = supabase.table("tracking_sessions").insert({
                            "vehicle_id": v_id,
                            "route_id": route_id,
                            "driver_id": driver_id,
                            "status": "completed",
                            "start_time": actual_start or start_time,
                            "end_time": actual_end or end_time,
                            "total_distance_km": 0,
                            "points_visited": len(points)
                        }).execute()
                        
                        if session_resp.data:
                            s_id = session_resp.data[0]['id']
                            # Mirror logs to tracking_logs for dashboard history
                            tracking_logs = []
                            for p in points:
                                ts = ensure_ist(p.get('deviceTimestamp'))
                                tracking_logs.append({
                                    "session_id": s_id,
                                    "timestamp": ts,
                                    "latitude": p.get('lat'),
                                    "longitude": p.get('long'),
                                    "speed": p.get('speed'),
                                    "accuracy": 10
                                })
                            for i in range(0, len(tracking_logs), chunk_size_logs):
                                supabase.table("tracking_logs").insert(tracking_logs[i:i+chunk_size_logs]).execute()

                        print(f"✅ Created session for {v['registration_number']}")
                    else:
                        print(f"⚠️ Could not map session for {v['registration_number']} (Missing route/driver)")

                except Exception as e:
                    print(f"❌ Error processing vehicle {tid}: {e}")

    except Exception as e:
        print(f"❌ Error in backfill: {e}")
