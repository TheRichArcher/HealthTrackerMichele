# check_db.py
import os
import sys
import psycopg2

def check_username_field():
    try:
        # Get database URL from environment or use a default
        database_url = os.environ.get('DATABASE_URL')
        
        if not database_url:
            print("DATABASE_URL not found in environment variables.")
            print("Please enter your database connection details:")
            dbname = input("Database name: ")
            user = input("Database user: ")
            password = input("Database password: ")
            host = input("Database host (default: localhost): ") or "localhost"
            port = input("Database port (default: 5432): ") or "5432"
            
            # Connect to database with provided details
            conn = psycopg2.connect(
                dbname=dbname,
                user=user,
                password=password,
                host=host,
                port=port
            )
        else:
            # Connect to database with URL
            conn = psycopg2.connect(database_url)
        
        # Create a cursor
        cur = conn.cursor()
        
        # Check if username column exists in users table
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='username'
        """)
        
        result = cur.fetchone()
        
        if result:
            print("✅ Username field exists in the database.")
            return True
        else:
            print("❌ Username field does not exist in the database.")
            print("The field needs to be added to the database.")
            
            add_field = input("Would you like to add the username field to the database now? (y/n): ")
            if add_field.lower() == 'y':
                cur.execute("ALTER TABLE users ADD COLUMN username VARCHAR(50) UNIQUE")
                conn.commit()
                print("✅ Username field added successfully to the database.")
                return True
            else:
                print("Field not added. You'll need to add it manually.")
                return False
            
    except Exception as e:
        print(f"❌ Error checking username field: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    exists = check_username_field()
    sys.exit(0 if exists else 1)