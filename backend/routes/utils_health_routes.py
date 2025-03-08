from flask import Blueprint, request, jsonify
from backend.extensions import db
import logging
import datetime

# Logger setup
logger = logging.getLogger("utils_health_routes")

# Create Flask Blueprint
utils_health_bp = Blueprint("utils_health_routes", __name__)

@utils_health_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify API status."""
    logger.info("Health check requested.")
    return jsonify({"status": "healthy", "message": "The API is running smoothly."})

@utils_health_bp.route("/metadata", methods=["GET"])
def get_metadata():
    """Returns metadata about the application."""
    metadata = {
        "app_name": "Health Tracker AI",
        "version": "1.0.0",
        "author": "HealthTrackerAI Team",
        "description": "A comprehensive tool for logging and tracking health symptoms and generating reports.",
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }
    logger.info("Metadata request received.")
    return jsonify(metadata)

@utils_health_bp.route("/log_request", methods=["POST"])
def log_request():
    """Logs incoming request data for debugging."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided."}), 400

        logger.debug(f"Request data received: {data}")
        return jsonify({"message": "Request data logged successfully."})

    except Exception as e:
        logger.error(f"Error logging request data: {str(e)}")
        return jsonify({"error": "An error occurred while logging request data."}), 500

@utils_health_bp.route("/db-health", methods=["GET"])
def db_health_check():
    """Check the health of the database connection."""
    try:
        result = db.session.execute("SELECT 1").scalar()  # ✅ Correct SQLAlchemy query
        if result == 1:
            logger.info("Database health check successful.")
            return jsonify({"status": "healthy", "message": "Database connection is active."})
        else:
            logger.warning("Database health check returned an unexpected result.")
            return jsonify({"error": "Database health check returned an unexpected response."}), 500
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}", exc_info=True)
        return jsonify({"error": "Database connection error. Please check logs for details."}), 500