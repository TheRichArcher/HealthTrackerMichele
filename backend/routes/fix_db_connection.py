import os
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get the database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

logger.info(f"Original DATABASE_URL: {DATABASE_URL}")

# Modify the URL to handle SSL properly
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

if DATABASE_URL.startswith("postgresql://"):
    # Add SSL mode parameter if not already present
    if "sslmode=" not in DATABASE_URL:
        # Check for existing query parameters
        if "?" in DATABASE_URL:
            DATABASE_URL += "&sslmode=require"
        else:
            DATABASE_URL += "?sslmode=require"
    # Optionally allow customization based on environment
    elif "sslmode=disable" in DATABASE_URL:
        logger.warning("SSL mode is disabled, which is insecure for production")

logger.info(f"Modified DATABASE_URL: {DATABASE_URL}")

# Create and test the connection
try:
    logger.info("Testing database connection...")
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_pre_ping=True
    )
    
    # Test the connection with a context manager to ensure proper cleanup
    with engine.connect() as connection:
        result = connection.execute("SELECT 1")
        row = result.fetchone()
        if row and row[0] == 1:
            logger.info("Connection successful!")
        else:
            raise Exception("Unexpected result from SELECT 1")
            
    # Dispose of the engine to free resources
    engine.dispose()
    logger.info("Connection test completed and resources cleaned up")

except OperationalError as e:
    logger.error(f"Database connection error: {str(e)}")
    raise  # Re-raise to ensure the error is propagated
except Exception as e:
    logger.error(f"Unexpected error during connection test: {str(e)}")
    raise