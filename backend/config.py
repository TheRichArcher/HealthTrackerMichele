import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup basic logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()  # Log to console
    ]
)

logger = logging.getLogger(__name__)
logger.info("Config module loaded with logging enabled")

def strtobool(val: str) -> bool:
    """Convert a string to a boolean value."""
    return val.lower() in ("yes", "true", "t", "1")

class Config:
    # JWT Configuration (Ensuring JWT_SECRET_KEY is explicitly set)
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    if not JWT_SECRET_KEY:
        raise ValueError("\u274c JWT_SECRET_KEY is missing from the environment. Please set it explicitly in .env or Render.")

    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", "86400"))  # 1 day (was 3600 seconds = 1 hour)
    JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", "2592000"))  # 30 days

    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///health_tracker.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    # Application Configuration
    DEBUG = strtobool(os.getenv("DEBUG", "0"))

    # CORS Configuration
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "https://healthtrackermichele.onrender.com,http://localhost:3000").split(",")
    CORS_HEADERS = ["Content-Type", "Authorization"]
    CORS_SUPPORTS_CREDENTIALS = True

    # Stripe Configuration
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

    # Stripe Product IDs
    STRIPE_PRO_PLAN_PRICE_ID = os.getenv("STRIPE_PRO_PLAN_PRICE_ID")  # $9.99/month
    STRIPE_ONE_TIME_PRICE_ID = os.getenv("STRIPE_ONE_TIME_PRICE_ID")  # $4.99 one-time

    # Subscription Pricing (in cents)
    SUBSCRIPTION_PRICE_MONTHLY = 999  # $9.99
    ONE_TIME_REPORT_PRICE = 499  # $4.99