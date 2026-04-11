import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Supabase Configuration
SUPABASE_URL = os.getenv("VITE_SUPABASE_URL")
# Use Service Role Key for background tasks to bypass RLS
SUPABASE_KEY = os.getenv("VITE_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in environment.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# GPS API Configuration
GPS_API_BASE = "https://externalapi.autonautics.com.au/api"
GPS_USER = "jatin@inwaste.co"
GPS_PASS = "Jatin@213"
