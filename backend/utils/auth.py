import jwt
import uuid
from functools import wraps
from flask import request, jsonify, current_app
from datetime import datetime, timedelta

def generate_temp_user_id(request):
    """Generate a temporary user ID for unauthenticated users."""
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
    return f"temp_{session_id}"

def token_required(f):
    """Decorator to ensure a valid JWT token is present in the request."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(" ")[1]

        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            data = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            current_user = {'user_id': data['user_id'], 'exp': data['exp']}
            if datetime.utcnow().timestamp() > current_user['exp']:
                return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        return f(current_user=current_user, *args, **kwargs)

    return decorated