from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
    get_jwt
)
from backend.extensions import db, bcrypt
from backend.models import User, RevokedToken
from datetime import datetime
import logging
import re
from sqlalchemy.exc import OperationalError
from flask import current_app
from flask_cors import cross_origin  # Import CORS support

# Logger setup
logger = logging.getLogger("user_routes")

# Create Flask Blueprint
user_routes = Blueprint("user_routes", __name__)

def is_valid_email(email):
    """Check if the provided string is a valid email."""
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email) is not None

@user_routes.route("/login", methods=["POST"])
@cross_origin()  # Allow CORS for this route
def login():
    """Handle user login and token generation."""
    try:
        data = request.get_json()
        login_id = data.get("username") or data.get("email")
        password = data.get("password")

        logger.debug(f"Login attempt with login_id: {login_id}")

        if not login_id or not password:
            return jsonify({"error": "Email/username and password are required."}), 400

        # Try to find user by email or username
        if is_valid_email(login_id):
            user = User.query.filter(User.email == login_id, User.deleted_at.is_(None)).first()
        else:
            user = User.query.filter(User.username == login_id, User.deleted_at.is_(None)).first()
            if not user:
                # If username not found, try as email as fallback
                user = User.query.filter(User.email == login_id, User.deleted_at.is_(None)).first()

        if not user or not user.check_password(password):
            return jsonify({"error": "Invalid email/username or password."}), 401

        # Create tokens with user.id as a string to avoid 'Subject must be a string' warning
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))

        logger.debug(f"Login successful for user_id: {user.id}, access_token: {access_token[:20]}...")

        return jsonify({
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user.id,
            "email": user.email,
            "username": user.username or user.email.split('@')[0],
            "subscription_tier": user.subscription_tier.value
        }), 200

    except OperationalError as e:
        logger.error(f"Database error during login: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection failed. Please try again later."}), 500
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        return jsonify({"error": f"Login failed: {str(e)}"}), 500

@user_routes.route("/auth/refresh/", methods=["POST"])
@jwt_required(refresh=True)
@cross_origin()
def refresh():
    """Refresh access token."""
    try:
        # Log the raw Authorization header for debugging
        auth_header = request.headers.get('Authorization', '')
        logger.debug(f"Refresh token request - Authorization header: {auth_header}")

        current_user_id = get_jwt_identity()
        logger.debug(f"Refreshing token for user_id: {current_user_id}")
        new_access_token = create_access_token(identity=current_user_id)
        logger.debug(f"New access token generated: {new_access_token[:20]}...")

        return jsonify({
            "access_token": new_access_token
        }), 200

    except OperationalError as e:
        logger.error(f"Database error during token refresh: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection failed. Please try again later."}), 500
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}", exc_info=True)
        return jsonify({"error": f"Error refreshing access token: {str(e)}"}), 500

@user_routes.route("/users", methods=["POST"])
@cross_origin()
def create_user():
    """Create a new user."""
    try:
        data = request.get_json()
        email = data.get("email") or data.get("username")
        username = data.get("username")
        password = data.get("password")

        logger.debug(f"Signup attempt with email: {email}, username: {username}")

        # Validate email
        if not email or not is_valid_email(email):
            return jsonify({"error": "Valid email is required."}), 400
        
        if not password:
            return jsonify({"error": "Password is required."}), 400

        # Check if email already exists
        existing_email = User.query.filter(User.email == email, User.deleted_at.is_(None)).first()
        if existing_email:
            return jsonify({"error": "Email already exists."}), 409

        # Check if username already exists (if provided)
        if username:
            existing_username = User.query.filter(User.username == username, User.deleted_at.is_(None)).first()
            if existing_username:
                return jsonify({"error": "Username already exists."}), 409
        else:
            # Generate a default username from email if not provided
            username = email.split('@')[0]
            # Check if generated username exists
            count = 1
            base_username = username
            while User.query.filter(User.username == username, User.deleted_at.is_(None)).first():
                username = f"{base_username}{count}"
                count += 1

        # Create new user
        new_user = User(
            email=email,
            username=username,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        # Create tokens with user.id as a string to avoid 'Subject must be a string' warning
        access_token = create_access_token(identity=str(new_user.id))
        refresh_token = create_refresh_token(identity=str(new_user.id))

        logger.info(f"User created: {new_user.email} with username {new_user.username}")
        return jsonify({
            "message": "User created successfully.",
            "user_id": new_user.id,
            "email": new_user.email,
            "username": new_user.username,
            "subscription_tier": new_user.subscription_tier.value,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "created_at": new_user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }), 201

    except OperationalError as e:
        db.session.rollback()
        logger.error(f"Database error during user creation: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection failed. Please try again later."}), 500
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating user: {str(e)}", exc_info=True)
        return jsonify({"error": f"Signup failed: {str(e)}"}), 500

@user_routes.route("/users/me", methods=["GET"])
@jwt_required()
@cross_origin()
def get_current_user():
    """Fetch current user information."""
    try:
        # Log the raw Authorization header for debugging
        auth_header = request.headers.get('Authorization', '')
        logger.debug(f"Get current user request - Authorization header: {auth_header}")

        current_user_id = get_jwt_identity()
        user = User.query.filter(User.id == int(current_user_id), User.deleted_at.is_(None)).first()
        if not user:
            return jsonify({"error": "User not found."}), 404

        return jsonify({
            "id": user.id,
            "email": user.email,
            "username": user.username or user.email.split('@')[0],
            "subscription_tier": user.subscription_tier.value,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    except OperationalError as e:
        logger.error(f"Database error fetching current user: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection failed. Please try again later."}), 500
    except Exception as e:
        logger.error(f"Error fetching current user: {str(e)}", exc_info=True)
        return jsonify({"error": f"An error occurred while fetching user: {str(e)}"}), 500

@user_routes.route("/", methods=["GET"])
@jwt_required()
@cross_origin()
def get_users():
    """Fetch a list of users with pagination."""
    try:
        # Log the raw Authorization header for debugging
        auth_header = request.headers.get('Authorization', '')
        logger.debug(f"Get users request - Authorization header: {auth_header}")

        skip = int(request.args.get("skip", 0))
        limit = int(request.args.get("limit", 100))

        users = User.query.filter(User.deleted_at.is_(None)).offset(skip).limit(limit).all()
        total_count = User.query.filter(User.deleted_at.is_(None)).count()

        return jsonify({
            "users": [{
                "id": u.id,
                "email": u.email,
                "username": u.username or u.email.split('@')[0],
                "subscription_tier": u.subscription_tier.value,
                "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S")
            } for u in users],
            "total_count": total_count,
        })

    except OperationalError as e:
        logger.error(f"Database error fetching users: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection failed. Please try again later."}), 500
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}", exc_info=True)
        return jsonify({"error": f"An error occurred while fetching users: {str(e)}"}), 500

@user_routes.route("/<int:user_id>", methods=["GET"])
@jwt_required()
@cross_origin()
def get_user(user_id):
    """Fetch user information by user ID."""
    try:
        # Log the raw Authorization header for debugging
        auth_header = request.headers.get('Authorization', '')
        logger.debug(f"Get user request for user_id {user_id} - Authorization header: {auth_header}")

        current_user_id = get_jwt_identity()
        if int(current_user_id) != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.filter(User.id == user_id, User.deleted_at.is_(None)).first()
        if not user:
            return jsonify({"error": "User not found."}), 404

        return jsonify({
            "id": user.id,
            "email": user.email,
            "username": user.username or user.email.split('@')[0],
            "subscription_tier": user.subscription_tier.value,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    except OperationalError as e:
        logger.error(f"Database error fetching user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection failed. Please try again later."}), 500
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"An error occurred while fetching the user: {str(e)}"}), 500

@user_routes.route("/<int:user_id>", methods=["PUT"])
@jwt_required()
@cross_origin()
def update_user(user_id):
    """Update user information by user ID."""
    try:
        # Log the raw Authorization header for debugging
        auth_header = request.headers.get('Authorization', '')
        logger.debug(f"Update user request for user_id {user_id} - Authorization header: {auth_header}")

        current_user_id = get_jwt_identity()
        if int(current_user_id) != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.filter(User.id == user_id, User.deleted_at.is_(None)).first()
        if not user:
            return jsonify({"error": "User not found."}), 404

        data = request.get_json()
        
        # Update username if provided
        if "username" in data:
            new_username = data.get("username")
            if new_username:
                # Check if username already exists
                existing_username = User.query.filter(
                    User.username == new_username, 
                    User.deleted_at.is_(None), 
                    User.id != user.id
                ).first()
                if existing_username:
                    return jsonify({"error": "Username already exists."}), 409
                user.username = new_username
        
        # Update email if provided
        if "email" in data:
            new_email = data.get("email")
            if new_email:
                if not is_valid_email(new_email):
                    return jsonify({"error": "Invalid email format."}), 400
                # Check if email already exists
                existing_email = User.query.filter(
                    User.email == new_email, 
                    User.deleted_at.is_(None), 
                    User.id != user.id
                ).first()
                if existing_email:
                    return jsonify({"error": "Email already exists."}), 409
                user.email = new_email
        
        user.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            "message": "User updated successfully.",
            "user_id": user.id,
            "email": user.email,
            "username": user.username or user.email.split('@')[0],
            "subscription_tier": user.subscription_tier.value,
            "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    except OperationalError as e:
        db.session.rollback()
        logger.error(f"Database error updating user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection failed. Please try again later."}), 500
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"An error occurred while updating user: {str(e)}"}), 500

@user_routes.route("/<int:user_id>/password", methods=["PUT"])
@jwt_required()
@cross_origin()
def update_password(user_id):
    """Update user password by user ID."""
    try:
        # Log the raw Authorization header for debugging
        auth_header = request.headers.get('Authorization', '')
        logger.debug(f"Update password request for user_id {user_id} - Authorization header: {auth_header}")

        current_user_id = get_jwt_identity()
        if int(current_user_id) != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.filter(User.id == user_id, User.deleted_at.is_(None)).first()
        if not user:
            return jsonify({"error": "User not found."}), 404

        data = request.get_json()
        current_password = data.get("current_password")
        new_password = data.get("new_password")

        if not current_password or not new_password:
            return jsonify({"error": "Current and new passwords are required."}), 400

        if not user.check_password(current_password):
            return jsonify({"error": "Invalid current password."}), 400

        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"message": "Password updated successfully.", "user_id": user.id})

    except OperationalError as e:
        db.session.rollback()
        logger.error(f"Database error updating password for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection failed. Please try again later."}), 500
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating password for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"An error occurred while updating password: {str(e)}"}), 500

@user_routes.route("/<int:user_id>", methods=["DELETE"])
@jwt_required()
@cross_origin()
def delete_user(user_id):
    """Delete a user by user ID."""
    try:
        # Log the raw Authorization header for debugging
        auth_header = request.headers.get('Authorization', '')
        logger.debug(f"Delete user request for user_id {user_id} - Authorization header: {auth_header}")

        current_user_id = get_jwt_identity()
        if int(current_user_id) != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.filter(User.id == user_id, User.deleted_at.is_(None)).first()
        if not user:
            return jsonify({"error": "User not found."}), 404

        # Use soft delete
        user.deleted_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"message": "User deleted successfully.", "user_id": user.id})

    except OperationalError as e:
        db.session.rollback()
        logger.error(f"Database error deleting user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection failed. Please try again later."}), 500
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"An error occurred while deleting user: {str(e)}"}), 500

@user_routes.route("/auth/validate/", methods=["GET"])
@jwt_required()
@cross_origin()
def validate_token():
    """Validate an access token by ensuring it's still valid."""
    try:
        # Log the raw Authorization header for debugging
        auth_header = request.headers.get('Authorization', '')
        logger.debug(f"Validate token request - Authorization header: {auth_header}")

        current_user_id = get_jwt_identity()
        user = User.query.filter(User.id == int(current_user_id), User.deleted_at.is_(None)).first()
        if not user:
            logger.warning(f"Token validation failed: User {current_user_id} not found")
            return jsonify({"error": "User not found"}), 404
            
        logger.info(f"Token validated successfully for user_id: {current_user_id}")
        return jsonify({
            "message": "Token is valid",
            "user_id": current_user_id,
            "email": user.email,
            "username": user.username or user.email.split('@')[0],
            "subscription_tier": user.subscription_tier.value
        }), 200
    except OperationalError as e:
        logger.error(f"Database error during token validation: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection failed. Please try again later."}), 500
    except Exception as e:
        logger.error(f"Token validation failed for user_id {current_user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"Invalid or expired token: {str(e)}"}), 401