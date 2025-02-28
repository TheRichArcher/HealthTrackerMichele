import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def strtobool(val: str) -> bool:
    """Convert a string to a boolean value."""
    return val.lower() in ("yes", "true", "t", "1")

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("\u274c SECRET_KEY is missing from the environment. Please set it in .env.")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///health_tracker.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    DEBUG = strtobool(os.getenv("DEBUG", "0"))  # ✅ More reliable boolean handling
    CORS_HEADERS = "Content-Type"
    
    # ✅ Stripe configuration
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

    # ✅ Stripe product IDs
    STRIPE_PRO_PLAN_PRICE_ID = os.getenv("STRIPE_PRO_PLAN_PRICE_ID")  # $9.99/month
    STRIPE_ONE_TIME_PRICE_ID = os.getenv("STRIPE_ONE_TIME_PRICE_ID")  # $4.99 one-time

    # ✅ Subscription pricing (in cents)
    SUBSCRIPTION_PRICE_MONTHLY = 999  # $9.99
    ONE_TIME_REPORT_PRICE = 499  # $4.99