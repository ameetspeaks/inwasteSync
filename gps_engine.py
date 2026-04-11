from datetime import datetime
from gps_config import supabase

def fetch_districts_and_vehicles():
    """Fetches all districts and their associated GPS vehicles."""
    vehicles = supabase.table("vehicles").select("id, gps_tracked_item_id, registration_number, village_id, last_gps_sync, ignition_off_count, driver_id").eq("has_gps", True).execute()
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

def process_gps_points(points, v_lookup, uid, v_to_session):
    """Processes points, updates vehicles, and inserts logs."""
    total_inserted = 0
    # Group points by vehicle to find the LATEST state
    vehicle_latest_point = {}
    for p in points:
        tid = str(p.get('trackedItemID'))
        ts = p.get('deviceTimestamp', '')
        # Ensure timestamp has IST offset if missing
        if ts and '+' not in ts and 'Z' not in ts.upper():
            ts = f"{ts}+05:30"
            p['deviceTimestamp'] = ts
            
        if tid not in vehicle_latest_point or ts > vehicle_latest_point[tid].get('deviceTimestamp', ''):
            vehicle_latest_point[tid] = p

    # 1. Update Vehicle Status based on LATEST point
    for tid, p in vehicle_latest_point.items():
        v = v_lookup.get(tid)
        if v:
            ignited = int(p.get('ignition', 0)) == 1
            new_off_count = 0 if ignited else (v.get('ignition_off_count', 0) + 1)
            
            supabase.table("vehicles").update({
                "last_gps_lat": float(p.get('lat', 0)),
                "last_gps_long": float(p.get('long', 0)),
                "last_gps_speed": float(p.get('speed', 0)),
                "is_ignited": ignited,
                "is_moving": int(p.get('movement', 0)) == 1,
                "last_gps_sync": datetime.now().isoformat(),
                "ignition_off_count": new_off_count
            }).eq("id", v['id']).execute()

    # 2. Insert Logs
    for p in points:
        tid = str(p.get('trackedItemID'))
        v = v_lookup.get(tid)
        if v:
            sid = v_to_session.get(v['id'])
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
                    "raw_data": p,
                    "session_id": sid
                }).execute()
                
                # Also insert into tracking_logs
                if sid:
                    supabase.table("tracking_logs").insert({
                        "session_id": sid,
                        "timestamp": p.get('deviceTimestamp'),
                        "latitude": p.get('lat'),
                        "longitude": p.get('long'),
                        "speed": p.get('speed'),
                        "accuracy": 10
                    }).execute()
                total_inserted += 1
            except Exception:
                pass 
    return total_inserted
