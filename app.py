import os
import logging
from datetime import timedelta
from flask import Flask, jsonify, request, send_from_directory, Blueprint
from dotenv import load_dotenv
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
    get_jwt,
)
from backend.extensions import db, bcrypt, cors, migrate
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from flask_cors import cross_origin

# Load environment variables
load_dotenv()

# Validate required environment variables
required_env_vars = ['JWT_SECRET_KEY', 'SECRET_KEY', 'DATABASE_URL']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    error_message = f"Missing required environment variables: {', '.join(missing_vars)}"
    print(f"❌ ERROR: {error_message}")
    raise RuntimeError(error_message)

# Configuration class for token expiry settings
class Config:
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)  # 1 hour
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)  # 30 days

def create_app():
    # Initialize Flask application
    app = Flask(
        __name__,
        static_folder=os.path.abspath('backend/static/dist'),
        static_url_path=''  # Serve static files from root
    )

    # Configure app with values from environment variables and Config
    app.config.update(
        JWT_SECRET_KEY=os.getenv('JWT_SECRET_KEY'),
        JWT_ACCESS_TOKEN_EXPIRES=Config.JWT_ACCESS_TOKEN_EXPIRES,
        JWT_REFRESH_TOKEN_EXPIRES=Config.JWT_REFRESH_TOKEN_EXPIRES,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.getenv('SECRET_KEY'),
        JWT_BLACKLIST_ENABLED=True,
        JWT_BLACKLIST_TOKEN_CHECKS=['access', 'refresh'],
        # Enhanced CORS configuration
        CORS_ORIGINS=os.getenv('CORS_ORIGINS', 'https://healthtrackermichele.onrender.com,http://localhost:3000').split(","),
        CORS_HEADERS=["Content-Type", "Authorization"],
        CORS_SUPPORTS_CREDENTIALS=True
    )

    # Logging Configuration
    logging.basicConfig(
        level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper()),
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(os.getenv('LOG_FILE', 'app.log')),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)

    # Log the JWT_SECRET_KEY with masking for security (be cautious in production)
    logger.info(f"JWT_SECRET_KEY loaded: {os.getenv('JWT_SECRET_KEY')[:6]}****")

    # Database Configuration
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set")
    logger.info(f"Original DATABASE_URL: {DATABASE_URL}")

    # Modify the URL to handle SSL and driver properly
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

    # Initialize SQLAlchemy engine with custom pool settings
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
        'pool_pre_ping': True
    }

    # Initialize extensions with updated CORS settings
    db.init_app(app)
    bcrypt.init_app(app)
    cors.init_app(app,
                  resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
                  allow_headers=app.config["CORS_HEADERS"],
                  supports_credentials=app.config["CORS_SUPPORTS_CREDENTIALS"])
    migrate.init_app(app, db)
    jwt = JWTManager(app)

    # Import models
    from backend.models import User, Symptom, SymptomLog, Report, HealthData, RevokedToken

    # Database initialization with connection test
    with app.app_context():
        try:
            # Test database connection before creating tables
            engine = create_engine(DATABASE_URL, **app.config['SQLALCHEMY_ENGINE_OPTIONS'])
            with engine.connect() as connection:
                result = connection.execute(text("SELECT 1"))
                row = result.fetchone()
                if row and row[0] == 1:
                    logger.info("✅ Database connection successful!")
                else:
                    raise Exception("Unexpected result from SELECT 1")
            # Proceed with table creation
            db.create_all()
            logger.info('✅ Database tables initialized.')
        except OperationalError as e:
            logger.critical(f"❌ Database connection error: {str(e)}")
            raise
        except Exception as e:
            logger.critical(f"❌ Database initialization failed: {str(e)}")
            raise

    # Token blacklist handler
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload["jti"]
        token = RevokedToken.query.filter_by(jti=jti).first()
        return token is not None

    # Import and register blueprints
    from backend.routes.symptom_routes import symptom_routes
    from backend.routes.health_data_routes import health_data_routes
    from backend.routes.report_routes import report_routes
    from backend.routes.user_routes import user_routes
    from backend.routes.utils_health_routes import utils_health_bp
    from backend.routes.library_routes import library_routes
    from backend.routes.onboarding_routes import onboarding_routes
    from backend.routes.data_exporter import data_exporter
    from backend.routes.subscription_routes import subscription_routes

    # Register blueprints with proper URL prefixes
    blueprints = [
        (symptom_routes, '/api/symptoms'),
        (health_data_routes, '/api/health-data'),
        (report_routes, '/api/reports'),
        (user_routes, '/api'),
        (utils_health_routes, '/api'),
        (library_routes, '/api/library'),
        (onboarding_routes, '/api/onboarding'),
        (data_exporter, '/api/export'),
        (subscription_routes, '/api/subscription')
    ]

    for blueprint, url_prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)

    # Create a new blueprint for top-level routes
    top_level_routes = Blueprint('top_level_routes', __name__)

    # Logout route (added from updated version)
    @top_level_routes.route('/logout/', methods=['POST'])
    @jwt_required()
    def logout():
        jti = get_jwt()['jti']
        revoked_token = RevokedToken(jti=jti)
        db.session.add(revoked_token)
        db.session.commit()
        return jsonify({'message': 'Logged out successfully'}), 200

    # Register the top-level blueprint
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

    # Debug endpoint to inspect token validation with production check
    @app.route('/api/debug/token', methods=['GET'])
    @jwt_required()
    def debug_token():
        try:
            # Disable in production for security
            if os.getenv("FLASK_ENV", "production") == "production":
                return jsonify({"error": "Token debugging is disabled in production"}), 403

            # Get the raw token from the Authorization header
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return jsonify({'error': 'Bearer token missing'}), 400
            token = auth_header.split(' ')[1]

            # Log the raw token
            logger.info(f"Debug Token: Raw token received: {token}")

            # Decode the token without verification to inspect its contents
            from jwt import decode as jwt_decode, exceptions as jwt_exceptions
            try:
                decoded_token = jwt_decode(token, options={"verify_signature": False})
                logger.info(f"Debug Token: Decoded token (unverified): {decoded_token}")
            except jwt_exceptions.DecodeError as e:
                logger.error(f"Debug Token: Failed to decode token: {str(e)}")
                return jsonify({'error': f'Token decode error: {str(e)}'}), 400

            # Attempt to validate the token using JWTManager
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
            logger.error(f"Debug Token: Validation failed: {str(e)}")
            return jsonify({'error': f'Token validation failed: {str(e)}'}), 500

    # Serve React Frontend with error handling
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve(path):
        if path.startswith('api/'):
            return {'error': 'Not Found'}, 404

        if path and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)

        try:
            return send_from_directory(app.static_folder, 'index.html')
        except FileNotFoundError:
            logger.error("index.html not found in the static directory")
            return jsonify({'error': 'Frontend application is missing'}), 404
        except Exception as e:
            logger.error(f"Error serving index.html: {str(e)}")
            return jsonify({'error': 'Failed to serve application'}), 500

    # Health check endpoint
    @app.route('/health', methods=['GET'])
    def health_check():
        try:
            db.session.execute(text("SELECT 1"))
            return {"status": "healthy", "database": "connected"}, 200
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return {"status": "unhealthy", "database": "disconnected"}, 500

    return app

# Create the application instance
app = create_app()

# WSGI application
application = app

# Run Flask application
if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))  # Default to Render's expected port
    app.logger.info(f'Starting server on port {port}')
    app.run(host='0.0.0.0', port=port, debug=os.getenv('DEBUG', 'False') == 'True')