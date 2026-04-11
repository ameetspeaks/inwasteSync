# InwasteSync: GPS Synchronization Engine

This module provides a robust, modular synchronization system between the Autonautics GPS API and the Inwaste Supabase database.

## Architecture

The code is organized into several focused modules to simplify maintenance:

- **gps_sync_engine.py**: The main entry point. Handles command-line arguments and coordinates the sync flow.
- **auth.py**: Manages API tokens. It checks the database first and only performs a fresh login if the cached token is close to expiry.
- **realtime.py**: Handles the incremental synchronization of GPS points (fetches the latest 15 minutes of data).
- **backfill.py**: Handles historical data ingestion for specific dates.
- **engine.py**: Contains shared database operations, including updating vehicle status and mapping logs to tracking sessions.
- **config.py**: Holds configuration constants and initializes the Supabase client.
- **utils.py**: Provides utility functions, such as an ISO-compliant date parser that handles varying sub-second precision.

## Key Features

1.  **Denormalized Mapping**: Logs are linked directly to `tracking_sessions` via `vehicle_id`, ensuring fast queries and compatibility with the Tracking Dashboard.
2.  **Smart Sync Intervals**: Intelligently skips synchronization for vehicles with prolonged "Ignition OFF" status to save API quota and resources.
3.  **Resilient Parsing**: Custom date parser ensures compatibility across different Python versions by normalizing fractional second precision.
4.  **Automatic Deduplication**: Uses database-level unique constraints on `gps_live_logs` to prevent duplicate telemetry data.

## Automation

Tasks are automated via GitHub Actions:
1.  **Real-time Sync**: Runs every 5 minutes (`gps_sync_realtime.yml`).
2.  **Manual Backfill**: Triggerable via "Run workflow" with a custom date (`gps_manual_backfill.yml`).
3.  **Token Health**: Refreshes tokens and validates connection on every code push (`gps_token_health.yml`).

## Running Locally

```bash
cd inwastesync
pip install -r requirements.txt
python gps_sync_engine.py
```
