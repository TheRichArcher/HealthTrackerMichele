from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
    get_jwt
)
from backend.routes.extensions import db, bcrypt
from backend.models import User
from datetime import datetime, timedelta
import logging

# Enhanced logger setup
logger = logging.getLogger("user_routes")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Create Flask Blueprint with API prefix
user_routes = Blueprint("user_routes", __name__, url_prefix="/api")

@user_routes.route("/auth/login/", methods=["POST"])
def login():
    """Handle user login and token generation."""
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({"error": "Username and password are required."}), 400

        # Case-insensitive username lookup
        user = User.query.filter(User.username.ilike(username)).first()
        if not user or not bcrypt.check_password_hash(user.password, password):
            return jsonify({"error": "Invalid username or password."}), 401

        # Create tokens
        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)

        logger.info(f"Successful login for user: {username}")
        return jsonify({
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user.id,
            "username": user.username
        }), 200

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({"error": "An error occurred during login."}), 500

@user_routes.route("/auth/refresh/", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            logger.warning(f"Token refresh failed: User {current_user_id} not found")
            return jsonify({"error": "User not found"}), 404

        new_access_token = create_access_token(identity=current_user_id)
        
        logger.info(f"Token refreshed for user: {user.username}")
        return jsonify({
            "access_token": new_access_token,
            "user_id": user.id,
            "username": user.username
        }), 200

    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return jsonify({"error": "Error refreshing access token."}), 500

@user_routes.route("/users/", methods=["POST"])
def create_user():
    """Create a new user."""
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({"error": "Username and password are required."}), 400

        # Case-insensitive username check
        existing_user = User.query.filter(User.username.ilike(username)).first()
        if existing_user:
            return jsonify({"error": "Username already exists."}), 409

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
        new_user = User(
            username=username,
            password=hashed_password,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.session.add(new_user)
        db.session.commit()

        # Create tokens for automatic login after signup
        access_token = create_access_token(identity=new_user.id)
        refresh_token = create_refresh_token(identity=new_user.id)

        logger.info(f"User created: {new_user.username}")
        return jsonify({
            "message": "User created successfully.",
            "user_id": new_user.id,
            "username": new_user.username,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "created_at": new_user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({"error": "An error occurred during signup."}), 500

@user_routes.route("/users/", methods=["GET"])
@jwt_required()
def get_users():
    """Fetch a list of users with pagination."""
    try:
        skip = int(request.args.get("skip", 0))
        limit = int(request.args.get("limit", 100))

        users = User.query.offset(skip).limit(limit).all()
        total_count = User.query.count()

        return jsonify({
            "users": [{
                "id": u.id,
                "username": u.username,
                "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S")
            } for u in users],
            "total_count": total_count,
        })

    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        return jsonify({"error": "An error occurred while fetching users."}), 500

@user_routes.route("/users/<int:user_id>/", methods=["GET"])
@jwt_required()
def get_user(user_id):
    """Fetch user information by user ID."""
    try:
        current_user_id = get_jwt_identity()
        if current_user_id != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        return jsonify({
            "id": user.id,
            "username": user.username,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {str(e)}")
        return jsonify({"error": "An error occurred while fetching the user."}), 500

@user_routes.route("/users/<int:user_id>/", methods=["PUT"])
@jwt_required()
def update_user(user_id):
    """Update user information by user ID."""
    try:
        current_user_id = get_jwt_identity()
        if current_user_id != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        data = request.get_json()
        new_username = data.get("username")
        
        if new_username:
            existing_user = User.query.filter(
                User.username.ilike(new_username),
                User.id != user_id
            ).first()
            if existing_user:
                return jsonify({"error": "Username already exists."}), 409
            user.username = new_username

        user.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            "message": "User updated successfully.",
            "user_id": user.id,
            "username": user.username,
            "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user {user_id}: {str(e)}")
        return jsonify({"error": "An error occurred while updating user."}), 500

@user_routes.route("/users/<int:user_id>/password/", methods=["PUT"])
@jwt_required()
def update_password(user_id):
    """Update user password by user ID."""
    try:
        current_user_id = get_jwt_identity()
        if current_user_id != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        data = request.get_json()
        current_password = data.get("current_password")
        new_password = data.get("new_password")

        if not current_password or not new_password:
            return jsonify({"error": "Current and new passwords are required."}), 400

        if not bcrypt.check_password_hash(user.password, current_password):
            return jsonify({"error": "Invalid current password."}), 400

        user.password = bcrypt.generate_password_hash(new_password).decode("utf-8")
        user.updated_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"Password updated for user: {user.username}")
        return jsonify({"message": "Password updated successfully.", "user_id": user.id})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating password for user {user_id}: {str(e)}")
        return jsonify({"error": "An error occurred while updating password."}), 500

@user_routes.route("/users/<int:user_id>/", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    """Delete a user by user ID."""
    try:
        current_user_id = get_jwt_identity()
        if current_user_id != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        username = user.username  # Store for logging
        db.session.delete(user)
        db.session.commit()

        logger.info(f"User deleted: {username}")
        return jsonify({"message": "User deleted successfully.", "user_id": user_id})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        return jsonify({"error": "An error occurred while deleting user."}), 500

@user_routes.route("/auth/validate/", methods=["GET"])
@jwt_required()
def validate_token():
    """Validate an access token and return user information."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            logger.warning(f"Token validation failed: User {current_user_id} not found")
            return jsonify({"valid": False, "error": "User not found"}), 404

        logger.info(f"Token validated for user: {user.username}")
        return jsonify({
            "valid": True,
            "user_id": current_user_id,
            "username": user.username
        }), 200

    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        return jsonify({"valid": False, "error": "Invalid or expired token"}), 401

@user_routes.route("/auth/logout/", methods=["POST"])
@jwt_required()
def logout():
    """Handle user logout."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        jti = get_jwt()["jti"]
        # You could add token to a blacklist here if implementing token invalidation
        
        logger.info(f"User logged out: {user.username if user else current_user_id}")
        return jsonify({"message": "Successfully logged out"}), 200

    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return jsonify({"error": "An error occurred during logout"}), 500