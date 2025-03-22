from flask import Flask, jsonify, request, send_from_directory
from flask_jwt_extended import JWTManager, jwt_required, get_jwt
from backend.extensions import db, bcrypt, migrate, cors
from backend.routes.health_data_routes import health_data_routes
from backend.routes.report_routes import report_routes
from backend.routes.subscription_routes import subscription_routes
from backend.routes.symptom_routes import symptom_routes
from backend.routes.user_routes import user_routes
from backend.routes.library_routes import library_routes
from backend.routes.onboarding_routes import onboarding_routes
from backend.models import RevokedToken
from sqlalchemy import text
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import sys

# Centralized API Configuration
API_CONFIG = {
    "BASE_URL": os.getenv("API_BASE_URL", "https://healthtrackermichele.onrender.com"),
    "CORS_ORIGINS": os.getenv("CORS_ORIGINS", "*"),
    "CORS_HEADERS": ["Content-Type", "Authorization"],
    "CORS_SUPPORTS_CREDENTIALS": True,
    "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY"),
    "SQLALCHEMY_DATABASE_URI": os.getenv("DATABASE_URL").replace("postgresql://", "postgresql+psycopg://") + "?sslmode=require" if os.getenv("DATABASE_URL") else None,
    "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    "STATIC_FOLDER": os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "static"),  # Point to backend/static
    "REPORTS_DIR": os.getenv("RENDER_DISK_PATH", "static/reports"),
    "LOG_DIR": os.getenv("LOG_DIR", "logs"),
    "ENV": os.getenv("FLASK_ENV", "production")
}

def validate_env_vars():
    """Validate required environment variables."""
    required_vars = ["JWT_SECRET_KEY", "SQLALCHEMY_DATABASE_URI"]
    missing_vars = [var for var in required_vars if not API_CONFIG[var]]
    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

def setup_logging(app):
    """Configure advanced logging with file and console handlers."""
    os.makedirs(API_CONFIG["LOG_DIR"], exist_ok=True)
    log_file = os.path.join(API_CONFIG["LOG_DIR"], "healthtracker.log")
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    console_handler = logging.StreamHandler(sys.stdout)
    
    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(log_format)
    console_handler.setFormatter(log_format)
    
    logging.getLogger().setLevel(logging.INFO if API_CONFIG["ENV"] == "production" else logging.DEBUG)
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().addHandler(console_handler)
    
    return logging.getLogger(__name__)

def create_app():
    """Initialize Flask application with full production-grade features."""
    validate_env_vars()

    app = Flask(__name__, static_folder=API_CONFIG["STATIC_FOLDER"], static_url_path="/static")
    app.config.update(API_CONFIG)

    # Log the database URL and static folder for debugging
    logger = setup_logging(app)
    logger.info(f"Original DATABASE_URL: {os.getenv('DATABASE_URL')}")
    logger.info(f"Modified DATABASE_URL: {app.config['SQLALCHEMY_DATABASE_URI']}")
    logger.info(f"Static folder set to: {app.static_folder}")

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        allow_headers=app.config["CORS_HEADERS"],
        supports_credentials=app.config["CORS_SUPPORTS_CREDENTIALS"]
    )
    jwt = JWTManager(app)

    logger.info("Starting HealthTracker Michele application...")

    # Database connection check
    with app.app_context():
        try:
            db.session.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful!")
        except Exception as e:
            logger.critical(f"Database connection failed: {str(e)}", exc_info=True)
            sys.exit(1)

    # Register all blueprints
    app.register_blueprint(health_data_routes, url_prefix="/api/health-data")
    app.register_blueprint(report_routes, url_prefix="/api/reports")
    app.register_blueprint(subscription_routes, url_prefix="/api/subscription")
    app.register_blueprint(symptom_routes, url_prefix="/api/symptoms")
    app.register_blueprint(user_routes, url_prefix="/api/users")
    app.register_blueprint(library_routes, url_prefix="/api/library")
    app.register_blueprint(onboarding_routes, url_prefix="/api/onboarding")

    # JWT token blacklist handling
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload["jti"]
        token = RevokedToken.query.filter_by(jti=jti).first()
        return token is not None

    # Custom JWT error handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({"error": "Token has expired"}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({"error": "Invalid token"}), 401

    @jwt.unauthorized_loader
    def unauthorized_callback(error):
        return jsonify({"error": "Authorization required"}), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({"error": "Token has been revoked"}), 401

    # Request logging middleware
    @app.before_request
    def log_request_info():
        logger.debug(f"Request: {request.method} {request.path} - Headers: {dict(request.headers)}")

    # Health check endpoint
    @app.route("/health", methods=["GET"])
    def health_check():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify({"status": "healthy", "database": "connected"}), 200
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}", exc_info=True)
            return jsonify({"status": "unhealthy", "database": "disconnected"}), 503

    # Logout route
    @app.route("/api/logout", methods=["POST"])
    @jwt_required()
    def logout():
        jti = get_jwt()["jti"]
        revoked_token = RevokedToken(jti=jti, revoked_at=datetime.utcnow())
        db.session.add(revoked_token)
        db.session.commit()
        logger.info(f"Token revoked: {jti}")
        return jsonify({"message": "Successfully logged out"}), 200

    # Debug token route (disabled in production)
    if API_CONFIG["ENV"] != "production":
        @app.route("/api/debug/token", methods=["GET"])
        @jwt_required()
        def debug_token():
            jwt_data = get_jwt()
            return jsonify({"token_data": jwt_data}), 200

    # Serve React frontend and PDF reports
    @app.route("/static/reports/<path:filename>")
    def serve_report(filename):
        return send_from_directory(API_CONFIG["REPORTS_DIR"], filename)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        static_folder = app.static_folder
        index_path = os.path.join(static_folder, "dist", "index.html")
        logger.info(f"Requested path: {path}")
        logger.info(f"Static folder: {static_folder}")
        logger.info(f"Index path: {index_path}")
        if not os.path.exists(index_path):
            logger.error(f"index.html not found at {index_path}")
            return jsonify({"error": "Frontend not found"}), 404
        if path and os.path.exists(os.path.join(static_folder, "dist", path)):
            logger.info(f"Serving asset: {path}")
            return send_from_directory(os.path.join(static_folder, "dist"), path)
        logger.info("Serving index.html")
        return send_from_directory(os.path.join(static_folder, "dist"), "index.html")

    # Custom error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Server error: {str(error)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

    # Handle OPTIONS preflight requests
    @app.route("/<path:path>", methods=["OPTIONS"])
    def handle_options(path):
        return jsonify({"status": "ok"}), 200

    return app

# Create the app at the module level for Gunicorn
app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Ensure tables are created
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)