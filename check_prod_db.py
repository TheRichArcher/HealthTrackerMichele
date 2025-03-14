import os
from dotenv import load_dotenv
import psycopg
import sys

# Load environment variables
load_dotenv()

# Get DATABASE_URL from environment or use a provided URL
if len(sys.argv) > 1:
    DATABASE_URL = sys.argv[1]
else:
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://richarcher@localhost:5432/health_tracker')

print(f"Connecting to: {DATABASE_URL}")

try:
    # Connect to the database
    with psycopg.connect(DATABASE_URL) as conn:
        # Create a cursor
        with conn.cursor() as cur:
            # Get the columns of the users table
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users'
                ORDER BY ordinal_position;
            """)
            
            # Fetch all results
            columns = cur.fetchall()
            
            print("Users table schema:")
            for column in columns:
                print(f"  {column[0]}: {column[1]}")
            
            # Check if email column exists
            email_exists = any(column[0] == 'email' for column in columns)
            print(f"\nEmail column exists: {email_exists}")
            
            if not email_exists:
                print("\nLet's add the email column:")
                try:
                    cur.execute("ALTER TABLE users ADD COLUMN email VARCHAR(255) UNIQUE;")
                    conn.commit()
                    print("Email column added successfully!")
                except Exception as e:
                    print(f"Error adding email column: {str(e)}")
except Exception as e:
    print(f"Error connecting to database: {str(e)}")
