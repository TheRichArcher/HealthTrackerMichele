from functools import wraps
from flask import jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
import logging

# Configure logging
logger = logging.getLogger(__name__)

def require_auth():
    """
    Decorator to require JWT authentication for protected routes.

    Ensures a valid JWT is present in the Authorization header.
    Returns 401 if authentication fails.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
                logger.debug(f"Authenticated request to {request.path}")
                return fn(*args, **kwargs)
            except Exception as e:
                logger.error(f"Authentication error at {request.path}: {str(e)}", exc_info=True)
                return jsonify({
                    "error": "Authentication required",
                    "message": "Please provide a valid token in the Authorization header."
                }), 401
        return wrapper
    return decorator

def require_same_user():
    """
    Decorator to ensure the authenticated user matches the requested user_id.

    Verifies JWT and checks if the token's user_id matches the target user_id in route params.
    Returns 403 if unauthorized, 401 if authentication fails.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
                current_user_id = get_jwt_identity()
                # Look for user_id in kwargs or view_args
                target_user_id = kwargs.get('user_id') or request.view_args.get('user_id')

                if not target_user_id:
                    logger.warning(f"No target user_id provided for {request.path}")
                    return jsonify({
                        "error": "Invalid request",
                        "message": "User ID is required for this operation."
                    }), 400

                if current_user_id != int(target_user_id):
                    logger.warning(f"User {current_user_id} attempted to access user {target_user_id} at {request.path}")
                    return jsonify({
                        "error": "Unauthorized access",
                        "message": "You can only access your own data."
                    }), 403

                logger.debug(f"Authorized user {current_user_id} for {request.path}")
                return fn(*args, **kwargs)
            except ValueError as e:
                logger.error(f"Invalid user_id format at {request.path}: {str(e)}", exc_info=True)
                return jsonify({
                    "error": "Invalid user_id",
                    "message": "User ID must be an integer."
                }), 400
            except Exception as e:
                logger.error(f"Authorization error at {request.path}: {str(e)}", exc_info=True)
                return jsonify({
                    "error": "Authorization failed",
                    "message": "Authentication or authorization error occurred."
                }), 401
        return wrapper
    return decorator