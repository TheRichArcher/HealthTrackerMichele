from functools import wraps
from flask import jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
import logging

logger = logging.getLogger("middleware")

def require_auth():
    """Decorator to require JWT authentication for routes."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
                return fn(*args, **kwargs)
            except Exception as e:
                logger.error(f"Authentication error: {str(e)}")
                return jsonify({"error": "Authentication required"}), 401
        return wrapper
    return decorator

def require_same_user():
    """Decorator to ensure the authenticated user matches the requested user_id."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
                current_user_id = get_jwt_identity()
                target_user_id = kwargs.get('user_id') or request.view_args.get('user_id')

                if not target_user_id or current_user_id != int(target_user_id):
                    return jsonify({"error": "Unauthorized access"}), 403

                return fn(*args, **kwargs)
            except Exception as e:
                logger.error(f"Authorization error: {str(e)}")
                return jsonify({"error": "Authorization failed"}), 401
        return wrapper
    return decorator