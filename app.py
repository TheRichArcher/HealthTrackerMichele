# backend/app.py
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import timedelta
from flask import Flask, send_from_directory, jsonify, request
from flask_jwt_extended import JWTManager, verify_jwt_in_request, get_jwt, get_jwt_identity
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from jwt import decode as jwt_decode, exceptions as jwt_exceptions
from backend.extensions import db, bcrypt, migrate, cors, init_extensions
from backend.routes.user_routes import user_routes
from backend.routes.symptom_routes import symptom_routes
from backend.routes.health_data_routes import health_data_routes
from backend.routes.report_routes import report_routes
from backend.routes.utils_health_routes import utils_health_bp
from backend.routes.library_routes import library_routes
from backend.routes.onboarding_routes import onboarding_routes
from backend.routes.data_exporter import data_exporter
from backend.routes.subscription_routes import subscription_routes
from backend.models import RevokedToken
from flask import Blueprint

# Load environment variables from .env file
load_dotenv()

# Validate required environment variables
required_env_vars = ['JWT_SECRET_KEY', 'SECRET_KEY', 'DATABASE_URL', 'STRIPE_SECRET_KEY', 'FRONTEND_URL']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    error_message = f"Missing required environment variables: {', '.join(missing_vars)}"
    print(f"❌ ERROR: {error_message}")
    raise RuntimeError(error_message)

# Initialize Flask app
app = Flask(
    __name__,
    static_folder=os.path.abspath('backend/static/dist'),
    static_url_path='/static'
)

# Configure DATABASE_URL for Render.com (replace 'postgresql://' with 'postgresql+psycopg://' and add sslmode)
database_url = os.getenv('DATABASE_URL', 'sqlite:///health_tracker.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://')
if database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    if 'sslmode' not in database_url:
        if "?" in database_url:
            database_url += "&sslmode=require"
        else:
            database_url += "?sslmode=require"
    elif "sslmode=disable" in database_url:
        print("WARNING: SSL mode is disabled, which is insecure for production")

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)  # 1 hour
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)  # 30 days
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'max_overflow': 20,
    'pool_timeout': 30,
    'pool_pre_ping': True
}
app.config['CORS_ORIGINS'] = os.getenv('CORS_ORIGINS', 'https://healthtrackermichele.onrender.com,http://localhost:5173,http://localhost:5000').split(',')
app.config['CORS_HEADERS'] = ['Content-Type', 'Authorization']
app.config['CORS_SUPPORTS_CREDENTIALS'] = True
app.config['FRONTEND_URL'] = os.getenv('FRONTEND_URL', 'https://healthtrackermichele.onrender.com')
app.config['JWT_BLACKLIST_ENABLED'] = True
app.config['JWT_BLACKLIST_TOKEN_CHECKS'] = ['access', 'refresh']

# Setup logging
log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()  # Changed to DEBUG for detailed logging
log_file = os.getenv('LOG_FILE', 'health_tracker.log')
numeric_level = getattr(logging, log_level, logging.DEBUG)
logger = logging.getLogger()
logger.setLevel(numeric_level)

# File handler with rotation
file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024*10, backupCount=5)
file_handler.setLevel(numeric_level)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(numeric_level)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logger.info(f"Resolved static folder: {app.static_folder}")
logger.info(f"JWT_SECRET_KEY loaded: {app.config['JWT_SECRET_KEY'][:5]}****")
logger.info(f"Original DATABASE_URL: {os.getenv('DATABASE_URL')}")
logger.info(f"Modified DATABASE_URL: {database_url}")

# Initialize JWT
jwt = JWTManager(app)

# Token blacklist handler
@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    token = RevokedToken.query.filter_by(jti=jti).first()
    return token is not None

# JWT error handlers
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({
        'status': 401,
        'sub_status': 42,
        'msg': 'Token has expired'
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({
        'status': 401,
        'sub_status': 43,
        'msg': 'Invalid token'
    }), 401

@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({
        'status': 401,
        'sub_status': 44,
        'msg': 'Missing authorization token'
    }), 401

@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return jsonify({
        'status': 401,
        'sub_status': 45,
        'msg': 'Token has been revoked'
    }), 401

# Initialize Flask extensions
init_extensions(app)

# Test database connection and initialize tables
with app.app_context():
    try:
        engine = create_engine(database_url, **app.config['SQLALCHEMY_ENGINE_OPTIONS'])
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            row = result.fetchone()
            if row and row[0] == 1:
                logger.info("✅ Database connection successful!")
            else:
                raise Exception("Unexpected result from SELECT 1")
    except OperationalError as e:
        logger.critical(f"❌ Database connection error: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.critical(f"❌ Database initialization failed: {str(e)}", exc_info=True)
        raise

# Note: Database tables are initialized via Alembic migrations (alembic upgrade head) during deployment.
# If running locally, ensure migrations are applied by running:
#   flask db init  # (if not already initialized)
#   flask db migrate
#   flask db upgrade

# Log all incoming requests
@app.before_request
def log_request():
    logger.debug(f"Request: {request.method} {request.path} from {request.headers.get('Origin')} with headers: {dict(request.headers)}")

# Register Blueprints
app.register_blueprint(user_routes, url_prefix='/api')
app.register_blueprint(symptom_routes, url_prefix='/api/symptoms')
app.register_blueprint(health_data_routes, url_prefix='/api/health-data')
app.register_blueprint(report_routes, url_prefix='/api/reports')
app.register_blueprint(utils_health_bp, url_prefix='/api')
app.register_blueprint(library_routes, url_prefix='/api/library')
app.register_blueprint(onboarding_routes, url_prefix='/api/onboarding')
app.register_blueprint(data_exporter, url_prefix='/api/export')
app.register_blueprint(subscription_routes, url_prefix='/api/subscription')

# Top-level routes for logout
top_level_routes = Blueprint('top_level_routes', __name__)

@top_level_routes.route('/logout/', methods=['POST'])
def logout():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'status': 401, 'sub_status': 44, 'msg': 'Missing authorization token'}), 401

    try:
        verify_jwt_in_request()
        jti = get_jwt()['jti']
        revoked_token = RevokedToken(jti=jti)
        db.session.add(revoked_token)
        db.session.commit()
        return jsonify({'message': 'Logged out successfully'}), 200
    except Exception as e:
        logger.error(f"Logout failed: {str(e)}", exc_info=True)
        return jsonify({'status': 500, 'msg': 'Internal server error'}), 500

app.register_blueprint(top_level_routes)

# CORS preflight OPTIONS handler
@app.route('/api/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    logger.debug(f"Handling OPTIONS request for /api/{path} from {request.headers.get('Origin')}")
    response = jsonify({})
    response.headers['Access-Control-Allow-Origin'] = 'https://healthtrackermichele.onrender.com'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response, 200

# Debug endpoint for token validation
@app.route('/api/debug/token', methods=['GET'])
def debug_token():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Bearer token missing'}), 400

    try:
        verify_jwt_in_request()
        if os.getenv("FLASK_ENV", "production") == "production":
            return jsonify({"error": "Token debugging is disabled in production"}), 403
        token = auth_header.split(' ')[1]
        logger.info(f"Debug Token: Raw token received: {token}")
        try:
            decoded_token = jwt_decode(token, options={"verify_signature": False})
            logger.info(f"Debug Token: Decoded token (unverified): {decoded_token}")
        except jwt_exceptions.DecodeError as e:
            logger.error(f"Debug Token: Failed to decode token: {str(e)}")
            return jsonify({'error': f'Token decode error: {str(e)}'}), 400
        current_user = get_jwt_identity()
        jwt_data = get_jwt()
        logger.info(f"Debug Token: Validated identity: {current_user}")
        logger.info(f"Debug Token: JWT data: {jwt_data}")
        return jsonify({
            'status': 'success',
            'message': 'Token validated',
            'identity': current_user,
            'jwt_data': jwt_data
        }), 200
    except Exception as e:
        logger.error(f"Debug Token: Validation failed: {str(e)}", exc_info=True)
        return jsonify({'error': f'Token validation failed: {str(e)}'}), 500

# Log registered routes
logger.info("=== Registered Routes ===")
for rule in app.url_map.iter_rules():
    logger.info(f"{rule.endpoint}: {rule}")
logger.info("=======================")

# Serve PDF reports
reports_dir = os.path.join('/opt/render/project/src/backend/static/reports')
os.makedirs(reports_dir, exist_ok=True)

@app.route('/static/reports/<path:filename>')
def serve_report(filename):
    logger.info(f"Serving report file: {filename}")
    if not os.path.exists(reports_dir):
        logger.error(f"Reports directory not found: {reports_dir}")
        return jsonify({'error': 'Reports directory not found'}), 404
    try:
        return send_from_directory(reports_dir, filename)
    except Exception as e:
        logger.error(f"Exception serving report file {filename}: {str(e)}", exc_info=True)
        return jsonify({'error': f'Failed to serve report file: {str(e)}'}), 500

# Serve React frontend
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    logger.info(f"Requested path: {path}")
    if path.startswith('api/'):
        logger.info("Path starts with 'api/', returning 404")
        return jsonify({'error': 'Not Found'}), 404

    # Serve known static assets
    if path.startswith('assets/') or path in ('doctor-avatar.png', 'user-avatar.png'):
        static_path = os.path.join(app.static_folder, path)
        if os.path.exists(static_path):
            logger.info(f"Serving static file: {static_path}")
            return send_from_directory(app.static_folder, path)
        else:
            logger.error(f"Static file not found: {static_path}")
            return jsonify({'error': 'Static file not found'}), 404

    # Serve index.html for all other paths
    index_path = os.path.join(app.static_folder, 'index.html')
    logger.info(f"Serving index.html for path: {path}")
    if not os.path.exists(index_path):
        logger.error("index.html not found in the static directory")
        return jsonify({'error': 'Frontend application is missing'}), 404

    try:
        logger.info("Serving index.html")
        return send_from_directory(app.static_folder, 'index.html')
    except Exception as e:
        logger.error(f"Exception serving index.html: {str(e)}", exc_info=True)
        return jsonify({'error': 'Server error while serving application'}), 500

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        return jsonify({"status": "unhealthy", "database": "disconnected"}), 500

# Error handling
@app.errorhandler(404)
def not_found(error):
    logger.warning(f"404 error: {str(error)}")
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500

# WSGI application
application = app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    app.logger.info(f'Starting server on port {port}')
    app.run(host='0.0.0.0', port=port, debug=os.getenv('DEBUG', 'False') == 'True')