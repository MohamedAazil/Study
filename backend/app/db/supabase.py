"""Supabase client helpers.

The backend talks to Supabase with the service-role key and enforces
authorization in application code (see ``app.auth``). RLS policies in
``supabase/migrations`` additionally protect any direct client access made
with the anon key + user JWT (e.g. from the frontend).
"""

from functools import lru_cache

from app.config import get_settings
from supabase import Client, create_client


class SupabaseNotConfiguredError(RuntimeError):
    pass


@lru_cache
def get_service_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SupabaseNotConfiguredError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_db() -> Client:
    """FastAPI dependency returning the shared service-role client."""
    return get_service_client()
