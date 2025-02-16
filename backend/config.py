import os
from dotenv import load_dotenv
from distutils.util import strtobool

# Load environment variables from .env file
load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("❌ SECRET_KEY is missing from the environment. Please set it in .env.")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///health_tracker.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    DEBUG = bool(strtobool(os.getenv("DEBUG", "0")))  # ✅ More reliable boolean handling
    CORS_HEADERS = "Content-Type"
