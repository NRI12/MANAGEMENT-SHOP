from supabase import create_client
from config import Config

supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)


def get_user_role(user_id: str) -> str:
    """
    Determine user role based on presence in customers table.
    If a row exists in `customers` for this user_id → 'customer', else 'admin'.
    """
    result = (
        supabase.table("customers")
        .select("user_id")
        .eq("user_id", user_id)
        .execute()
    )
    return "customer" if result.data else "admin"


