import os
import logging
from datetime import timedelta
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    get_jwt_identity, jwt_required, get_jwt
)
from backend.extensions import db, bcrypt, cors, migrate

# Load environment variables
load_dotenv()

# Validate required environment variables
required_env_vars = ['JWT_SECRET_KEY', 'SECRET_KEY', 'DATABASE_URL']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    error_message = f"Missing required environment variables: {', '.join(missing_vars)}"
    print(f"❌ ERROR: {error_message}")
    raise RuntimeError(error_message)

def create_app():
    # Initialize Flask application
    app = Flask(
        __name__,
        static_folder=os.path.abspath('backend/static/dist'),
        static_url_path=''  # Serve static files from root
    )

    # Configure app with values from environment variables
    app.config.update(
        JWT_SECRET_KEY=os.getenv('JWT_SECRET_KEY'),
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(seconds=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))),
        JWT_REFRESH_TOKEN_EXPIRES=timedelta(seconds=int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000))),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.getenv('SECRET_KEY'),
        JWT_BLACKLIST_ENABLED=True,
        JWT_BLACKLIST_TOKEN_CHECKS=['access', 'refresh']
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

    # Database Configuration
    DATABASE_URL = os.getenv('DATABASE_URL')
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    cors.init_app(app, resources={r"/*": {"origins": os.getenv('CORS_ORIGINS', '*')}})
    migrate.init_app(app, db)  # Initialize Flask-Migrate
    jwt = JWTManager(app)

    # Import models
    from backend.models import User, Symptom, SymptomLog, Report, HealthData, RevokedToken

    # Database initialization
    with app.app_context():
        try:
            db.create_all()
            logger.info('✅ Database connected and tables initialized.')
        except Exception as e:
            logger.critical(f"❌ Database initialization failed: {e}")
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
    from backend.routes.subscription_routes import subscription_bp

    # Register blueprints with proper URL prefixes
    blueprints = [
        (symptom_routes, '/api/symptoms'),
        (health_data_routes, '/api/health-data'),
        (report_routes, '/api/reports'),
        (user_routes, '/api'),
        (utils_health_bp, '/api'),
        (library_routes, '/api/library'),
        (onboarding_routes, '/api/onboarding'),
        (data_exporter, '/api/export'),
        (subscription_bp, '/api/subscription')
    ]

    for blueprint, url_prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)

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

    # Serve React Frontend
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve(path):
        if path.startswith('api/'):
            return {'error': 'Not Found'}, 404

        if path and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)

        try:
            return send_from_directory(app.static_folder, 'index.html')
        except Exception as e:
            logger.error(f"Error serving index.html: {str(e)}")
            return jsonify({'error': 'Failed to serve application'}), 500

    return app

# Create the application instance
app = create_app()

# WSGI application
application = app

# Run Flask application
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.logger.info(f'Starting server on port {port}')
    app.run(host='0.0.0.0', port=port, debug=os.getenv('DEBUG', 'False') == 'True')