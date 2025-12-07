import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    
    # Redirect URL for auth (password reset, email confirmation, etc.)
    # Default to localhost:5000 for Flask dev server
    REDIRECT_URL = os.getenv("REDIRECT_URL", "http://localhost:5000")

    # Basic Flask session security
    SESSION_COOKIE_SECURE = False  # set True behind HTTPS / in production
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


