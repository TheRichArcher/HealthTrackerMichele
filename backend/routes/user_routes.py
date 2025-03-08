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
from datetime import datetime, timedelta
import logging

# Logger setup
logger = logging.getLogger("user_routes")

# Create Flask Blueprint
user_routes = Blueprint("user_routes", __name__)

@user_routes.route("/login", methods=["POST"])
def login():
    """Handle user login and token generation."""
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({"error": "Username and password are required."}), 400

        user = User.query.without_deleted().filter_by(username=username).first()
        if not user or not bcrypt.check_password_hash(user.password, password):
            return jsonify({"error": "Invalid username or password."}), 401

        # Create tokens
        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)

        return jsonify({
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user.id,
            "username": user.username,
            "subscription_tier": user.subscription_tier.value
        }), 200

    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({"error": f"Login failed: {str(e)}"}), 500

@user_routes.route("/auth/refresh/", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token."""
    try:
        current_user_id = get_jwt_identity()
        new_access_token = create_access_token(identity=current_user_id)

        return jsonify({
            "access_token": new_access_token
        }), 200

    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        return jsonify({"error": f"Error refreshing access token: {str(e)}"}), 500

@user_routes.route("/users", methods=["POST"])
def create_user():
    """Create a new user."""
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({"error": "Username and password are required."}), 400

        existing_user = User.query.without_deleted().filter_by(username=username).first()
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
            "subscription_tier": new_user.subscription_tier.value,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "created_at": new_user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating user: {e}", exc_info=True)
        return jsonify({"error": f"Signup failed: {str(e)}"}), 500

@user_routes.route("/", methods=["GET"])
@jwt_required()
def get_users():
    """Fetch a list of users with pagination."""
    try:
        skip = int(request.args.get("skip", 0))
        limit = int(request.args.get("limit", 100))

        users = User.query.without_deleted().offset(skip).limit(limit).all()
        total_count = User.query.without_deleted().count()

        return jsonify({
            "users": [{
                "id": u.id,
                "username": u.username,
                "subscription_tier": u.subscription_tier.value,
                "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S")
            } for u in users],
            "total_count": total_count,
        })

    except Exception as e:
        logger.error(f"Error fetching users: {e}", exc_info=True)
        return jsonify({"error": f"An error occurred while fetching users: {str(e)}"}), 500

@user_routes.route("/<int:user_id>", methods=["GET"])
@jwt_required()
def get_user(user_id):
    """Fetch user information by user ID."""
    try:
        current_user_id = get_jwt_identity()
        if current_user_id != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.without_deleted().get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        return jsonify({
            "id": user.id,
            "username": user.username,
            "subscription_tier": user.subscription_tier.value,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {e}", exc_info=True)
        return jsonify({"error": f"An error occurred while fetching the user: {str(e)}"}), 500

@user_routes.route("/<int:user_id>", methods=["PUT"])
@jwt_required()
def update_user(user_id):
    """Update user information by user ID."""
    try:
        current_user_id = get_jwt_identity()
        if current_user_id != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.without_deleted().get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        data = request.get_json()
        user.username = data.get("username", user.username)
        user.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            "message": "User updated successfully.",
            "user_id": user.id,
            "username": user.username,
            "subscription_tier": user.subscription_tier.value,
            "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user {user_id}: {e}", exc_info=True)
        return jsonify({"error": f"An error occurred while updating user: {str(e)}"}), 500

@user_routes.route("/<int:user_id>/password", methods=["PUT"])
@jwt_required()
def update_password(user_id):
    """Update user password by user ID."""
    try:
        current_user_id = get_jwt_identity()
        if current_user_id != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.without_deleted().get(user_id)
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

        return jsonify({"message": "Password updated successfully.", "user_id": user.id})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating password for user {user_id}: {e}", exc_info=True)
        return jsonify({"error": f"An error occurred while updating password: {str(e)}"}), 500

@user_routes.route("/<int:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    """Delete a user by user ID."""
    try:
        current_user_id = get_jwt_identity()
        if current_user_id != user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        user = User.query.without_deleted().get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        # Use soft delete instead of hard delete
        user.soft_delete()

        return jsonify({"message": "User deleted successfully.", "user_id": user.id})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user {user_id}: {e}", exc_info=True)
        return jsonify({"error": f"An error occurred while deleting user: {str(e)}"}), 500

@user_routes.route("/auth/validate/", methods=["GET"])
@jwt_required()
def validate_token():
    """Validate an access token by ensuring it's still valid."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.without_deleted().get(current_user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
            
        return jsonify({
            "message": "Token is valid",
            "user_id": current_user_id,
            "username": user.username,
            "subscription_tier": user.subscription_tier.value
        }), 200
    except Exception as e:
        logger.error(f"Token validation error: {e}", exc_info=True)
        return jsonify({"error": f"Invalid or expired token: {str(e)}"}), 401

@user_routes.route("/logout/", methods=["POST"])
@jwt_required()
def logout():
    """Handle user logout and revoke the token."""
    try:
        jti = get_jwt()["jti"]
        # Add token to blacklist
        revoked_token = RevokedToken(jti=jti)
        db.session.add(revoked_token)
        db.session.commit()
        logger.info(f"Token revoked: {jti}")
        return jsonify({"message": "Successfully logged out"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Logout error: {e}", exc_info=True)
        return jsonify({"error": f"An error occurred during logout: {str(e)}"}), 500