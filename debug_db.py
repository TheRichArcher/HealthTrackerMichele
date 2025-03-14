import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get DATABASE_URL
DATABASE_URL = os.getenv('DATABASE_URL')
print(f"Original DATABASE_URL = {DATABASE_URL}")

# Apply transformations
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")
    print(f"After postgres:// replacement = {DATABASE_URL}")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
    print(f"After psycopg replacement = {DATABASE_URL}")

print(f"Final DATABASE_URL = {DATABASE_URL}")
