import argparse
import time
import sys
import os

# Ensure the root directory is in sys.path for robust imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from auth import get_gps_token
from realtime import sync_realtime
from backfill import backfill

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPS Sync Engine")
    parser.add_argument("--backfill", type=str, help="Date to backfill (YYYY-MM-DD)")
    parser.add_argument("--loop", action="store_true", help="Run in a continuous loop")
    parser.add_argument("--interval", type=int, default=300, help="Loop interval in seconds")
    
    args = parser.parse_args()
    
    # Initial token check
    token = get_gps_token()
    if not token:
        print("❌ Could not obtain token. Exiting.")
        exit(1)
        
    if args.backfill:
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
