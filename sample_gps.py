import json
import os

json_path = r'c:\Users\ameet\inwaste\docs\data\28-03-2026.json'
output_sql = r'c:\Users\ameet\inwaste\supabase\migrations\20260328160000_ingest_historical_gps_7733.sql'

with open(json_path, 'r') as f:
    raw_data = json.load(f)

data = raw_data['data']
total = len(data)
# Sample every 14th record to get ~500 points
step = max(1, total // 500)
sampled = data[::step]
# Ensure last record is included
if data[-1] not in sampled:
    sampled.append(data[-1])

sql_template = """-- Migration: Ingest historical GPS data for trackeditemid 7733
-- Generated on: 2026-03-28

DO $$
DECLARE
    v_vehicle_id UUID;
BEGIN
    SELECT id INTO v_vehicle_id FROM vehicles WHERE gps_tracked_item_id = '7733' LIMIT 1;
    
    IF v_vehicle_id IS NOT NULL THEN
        RAISE NOTICE 'Found vehicle for trackeditemid 7733, inserting % logs...', {count};
        
        -- Clean existing logs for this time period to avoid duplicates if re-run
        DELETE FROM public.gps_live_logs 
        WHERE vehicle_id = v_vehicle_id 
        AND last_sync_at >= '{start}' AND last_sync_at <= '{end}';

        -- Insert sampled live logs
        INSERT INTO public.gps_live_logs (vehicle_id, lat, lng, speed, is_ignited, last_sync_at, source)
        VALUES
{values};

        -- Insert or merge a trip segment
        INSERT INTO public.gps_trips (vehicle_id, start_time, end_time, start_lat, start_long, end_lat, end_long, status)
        VALUES (v_vehicle_id, '{start}', '{end}', {start_lat}, {start_long}, {end_lat}, {end_long}, 'completed');

        -- Update latest vehicle status
        UPDATE public.vehicles SET 
            last_gps_lat = {end_lat},
            last_gps_long = {end_long},
            last_gps_sync = '{end}',
            is_ignited = {final_ignited},
            is_moving = false,
            has_gps = true
        WHERE id = v_vehicle_id;

    ELSE
        RAISE WARNING 'Vehicle with trackeditemid 7733 not found in database.';
    END IF;
END $$;
"""

values_list = []
for p in sampled:
    ignited = 'true' if p['ignition'] == 1 else 'false'
    val = f"        (v_vehicle_id, {p['lat']}, {p['long']}, {p['speed']}, {ignited}, '{p['deviceTimestamp']}', 'DEVICE')"
    values_list.append(val)

values_str = ",\n".join(values_list)

start_p = data[0]
end_p = data[-1]

final_sql = sql_template.format(
    count=len(sampled),
    start=start_p['deviceTimestamp'],
    end=end_p['deviceTimestamp'],
    start_lat=start_p['lat'],
    start_long=start_p['long'],
    end_lat=end_p['lat'],
    end_long=end_p['long'],
    final_ignited=('true' if end_p['ignition'] == 1 else 'false'),
    values=values_str
)

with open(output_sql, 'w') as f:
    f.write(final_sql)

print(f"Generated SQL for {len(sampled)} points in {output_sql}")
