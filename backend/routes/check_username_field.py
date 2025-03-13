# check_username_field.py
from backend.extensions import db
from backend.models import User
import sys

def check_username_field():
    try:
        # Try to access the username attribute of the User model
        User.username
        print("✅ Username field exists in the User model.")
        
        # Check if it exists in the database
        try:
            # This query will fail if the column doesn't exist in the database
            db.session.query(User.username).limit(1).all()
            print("✅ Username field exists in the database.")
            return True
        except Exception as e:
            print(f"❌ Username field is in the model but not in the database: {e}")
            return False
            
    except AttributeError:
        print("❌ Username field does not exist in the User model.")
        return False

if __name__ == "__main__":
    # Import the Flask app and push an application context
    from app import app
    with app.app_context():
        exists = check_username_field()
        sys.exit(0 if exists else 1)