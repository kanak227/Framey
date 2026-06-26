import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Resolve the path to the root .env file
services_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(services_dir)
project_root = os.path.dirname(backend_dir)
env_path = os.path.join(project_root, ".env")

load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("VITE_SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("VITE_SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

def get_supabase_client() -> Client:
    """
    Returns a standard authenticated client using the Anon key.
    Useful for operations within request scopes or verifying tokens.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise ValueError("VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be configured in environment variables.")
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def get_supabase_service_client() -> Client:
    """
    Returns a service-role client that bypasses Row Level Security (RLS).
    Required by background workers to read/write jobs and upload storage files.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured in environment variables.")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
