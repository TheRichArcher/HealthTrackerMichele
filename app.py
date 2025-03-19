import os
import logging
from datetime import timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from jwt import decode as jwt_decode, exceptions as jwt_exceptions

# Load environment variables from a .env file (if present)
os.environ.setdefault('LOG_LEVEL', 'INFO')
os.environ.setdefault('LOG_FILE', 'app.log')
load_dotenv()

# Validate required environment variables
required_env_vars = ['JWT_SECRET_KEY', 'SECRET_KEY', 'DATABASE_URL', 'STRIPE_SECRET_KEY', 'FRONTEND_URL']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    error_message = f"Missing required environment variables: {', '.join(missing_vars)}"
    print(f"❌ ERROR: {error_message}")
    raise RuntimeError(error_message)

# Configuration class for token expiry settings
class Config:
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)  # Access token expires in 1 hour
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)  # Refresh token expires in 30 days

# Initialize Flask application
app = Flask(
    __name__,
    static_folder=os.path.abspath('backend/static/dist'),
    static_url_path='/static'  # Serve static files from /static/<filename>
)

# Set up logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL').upper()),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.getenv('LOG_FILE')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Log the resolved static folder path
logger.info(f"Resolved static folder: {app.static_folder}")

# Configure the Flask app with environment variables and settings
app.config.update(
    JWT_SECRET_KEY=os.getenv('JWT_SECRET_KEY'),
    JWT_ACCESS_TOKEN_EXPIRES=Config.JWT_ACCESS_TOKEN_EXPIRES,
    JWT_REFRESH_TOKEN_EXPIRES=Config.JWT_REFRESH_TOKEN_EXPIRES,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.getenv('SECRET_KEY'),
    JWT_BLACKLIST_ENABLED=True,
    JWT_BLACKLIST_TOKEN_CHECKS=['access', 'refresh'],
    CORS_ORIGINS=os.getenv('CORS_ORIGINS', 'https://healthtrackermichele.onrender.com,http://localhost:3000').split(","),
    CORS_HEADERS=["Content-Type", "Authorization"],
    CORS_SUPPORTS_CREDENTIALS=True,
    FRONTEND_URL=os.getenv('FRONTEND_URL', 'https://healthtrackermichele.onrender.com')  # Added FRONTEND_URL with default
)

# Log the JWT_SECRET_KEY with partial masking for security
logger.info(f"JWT_SECRET_KEY loaded: {os.getenv('JWT_SECRET_KEY')[:6]}****")

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")
logger.info(f"Original DATABASE_URL: {DATABASE_URL}")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
    if "sslmode=" not in DATABASE_URL:
        if "?" in DATABASE_URL:
            DATABASE_URL += "&sslmode=require"
        else:
            DATABASE_URL += "?sslmode=require"
    elif "sslmode=disable" in DATABASE_URL:
        logger.warning("SSL mode is disabled, which is insecure for production")

logger.info(f"Modified DATABASE_URL: {DATABASE_URL}")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'max_overflow': 20,
    'pool_timeout': 30,
    'pool_pre_ping': True
}

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
cors = CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}}, allow_headers=app.config["CORS_HEADERS"], supports_credentials=app.config["CORS_SUPPORTS_CREDENTIALS"])
migrate = Migrate(app, db)
jwt = JWTManager(app)

# Import models
from backend.models import User, Symptom, SymptomLog, Report, HealthData, RevokedToken

# Database initialization with connection test
with app.app_context():
    try:
        engine = create_engine(DATABASE_URL, **app.config['SQLALCHEMY_ENGINE_OPTIONS'])
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            row = result.fetchone()
            if row and row[0] == 1:
                logger.info("✅ Database connection successful!")
            else:
                raise Exception("Unexpected result from SELECT 1")
        db.create_all()
        logger.info('✅ Database tables initialized.')
    except OperationalError as e:
        logger.critical(f"❌ Database connection error: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.critical(f"❌ Database initialization failed: {str(e)}", exc_info=True)
        raise

# Token blacklist handler
@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    token = RevokedToken.query.filter_by(jti=jti).first()
    return token is not None

# Define blueprints
symptom_routes = Blueprint('symptom_routes', __name__, url_prefix='/api/symptoms')
health_data_routes = Blueprint('health_data_routes', __name__, url_prefix='/api/health-data')
report_routes = Blueprint('report_routes', __name__, url_prefix='/api/reports')
user_routes = Blueprint('user_routes', __name__, url_prefix='/api')
utils_health_bp = Blueprint('utils_health_routes', __name__, url_prefix='/api')
library_routes = Blueprint('library_routes', __name__, url_prefix='/api/library')
onboarding_routes = Blueprint('onboarding_routes', __name__, url_prefix='/api/onboarding')
data_exporter = Blueprint('data_exporter', __name__, url_prefix='/api/export')
subscription_routes = Blueprint('subscription_routes', __name__, url_prefix='/api/subscription')

# Register blueprints
app.register_blueprint(symptom_routes)
app.register_blueprint(health_data_routes)
app.register_blueprint(report_routes)
app.register_blueprint(user_routes)
app.register_blueprint(utils_health_bp)
app.register_blueprint(library_routes)
app.register_blueprint(onboarding_routes)
app.register_blueprint(data_exporter)
app.register_blueprint(subscription_routes)

# Create a blueprint for top-level routes
top_level_routes = Blueprint('top_level_routes', __name__)

@top_level_routes.route('/logout/', methods=['POST'])
def logout():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'status': 401, 'sub_status': 44, 'msg': 'Missing authorization token'}), 401

    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt
        verify_jwt_in_request()
        jti = get_jwt()['jti']
        from backend.models import RevokedToken
        revoked_token = RevokedToken(jti=jti)
        db.session.add(revoked_token)
        db.session.commit()
        return jsonify({'message': 'Logged out successfully'}), 200
    except Exception as e:
        logger.error(f"Logout failed: {str(e)}", exc_info=True)
        return jsonify({'status': 500, 'msg': 'Internal server error'}), 500

app.register_blueprint(top_level_routes)

# Debug logging for registered routes
logger.info("=== Registered Routes ===")
for rule in app.url_map.iter_rules():
    logger.info(f"{rule.endpoint}: {rule.rule}")
logger.info("=======================")

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

# Debug endpoint to inspect token validation
@app.route('/api/debug/token', methods=['GET'])
def debug_token():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Bearer token missing'}), 400

    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
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

# Serve React Frontend
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    logger.info(f"Requested path: {path}")
    if path.startswith('api/'):
        logger.info("Path starts with 'api/', returning 404")
        return {'error': 'Not Found'}, 404

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

# Serve PDF reports
@app.route('/static/reports/<path:filename>')
def serve_report(filename):
    logger.info(f"Serving report file: {filename}")
    reports_dir = os.path.join('/opt/render/project/src/backend/static/reports')
    if not os.path.exists(reports_dir):
        logger.error(f"Reports directory not found: {reports_dir}")
        return jsonify({'error': 'Reports directory not found'}), 404
    try:
        return send_from_directory(reports_dir, filename)
    except Exception as e:
        logger.error(f"Exception serving report file {filename}: {str(e)}", exc_info=True)
        return jsonify({'error': f'Failed to serve report file: {str(e)}'}), 500

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}, 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        return {"status": "unhealthy", "database": "disconnected"}, 500

# WSGI application
application = app

# Run Flask application
if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    app.logger.info(f'Starting server on port {port}')
    app.run(host='0.0.0.0', port=port, debug=os.getenv('DEBUG', 'False') == 'True')