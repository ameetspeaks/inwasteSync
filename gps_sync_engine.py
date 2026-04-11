import argparse
import time
import sys
import os

# Ensure the root directory is in sys.path for robust imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gps_auth import get_gps_token
from gps_realtime import sync_realtime
from gps_backfill import backfill, backfill_range

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPS Sync Engine")
    parser.add_argument("--backfill", type=str, help="Single date to backfill (YYYY-MM-DD)")
    parser.add_argument("--start_date", type=str, help="Start date for range backfill (YYYY-MM-DD)")
    parser.add_argument("--end_date", type=str, help="End date for range backfill (YYYY-MM-DD)")
    parser.add_argument("--loop", action="store_true", help="Run in a continuous loop")
    parser.add_argument("--interval", type=int, default=300, help="Loop interval in seconds")
    
    args = parser.parse_args()
    
    # Initial token check
    token = get_gps_token()
    if not token:
        print("❌ Could not obtain token. Exiting.")
        exit(1)
        
    if args.start_date and args.end_date:
        backfill_range(token, args.start_date, args.end_date)
    elif args.start_date:
        # If only start date is provided, backfill only that day
        backfill(token, args.start_date)
    elif args.backfill:
        backfill(token, args.backfill)
    elif args.loop:
        while True:
            # Refresh token every loop if needed
            token = get_gps_token()
            if not token:
                print("⚠️ Token refresh failed. Retrying in next cycle.")
            else:
                sync_realtime(token)
            
            print(f"😴 Sleeping for {args.interval}s...")
            time.sleep(args.interval)
    else:
        sync_realtime(token)
