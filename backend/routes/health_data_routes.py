# backend/routes/health_data_routes.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from backend.extensions import db
from backend.models import HealthData, User, UserTierEnum
import logging
from datetime import datetime
from backend.utils.openai_utils import call_openai_api

# Logger setup
logger = logging.getLogger("health_data_routes")
health_data_routes = Blueprint("health_data_routes", __name__, url_prefix="/api/health-data")

def is_premium_user(user):
    """Check if the user has a premium subscription tier."""
    return getattr(user, "subscription_tier", UserTierEnum.FREE.value) in {
        UserTierEnum.PAID.value,
        UserTierEnum.ONE_TIME.value
    }

# Route to fetch all health data
@health_data_routes.route("/", methods=["GET"])
def get_all_health_data():
    """Retrieve all health data records."""
    try:
        health_records = HealthData.query.all()
        return jsonify({"health_data": [
            {
                "id": record.id,
                "user_id": record.user_id,
                "data_type": record.data_type,
                "value": record.value,
                "recorded_at": record.recorded_at.strftime("%Y-%m-%d %H:%M:%S")
            } for record in health_records
        ]})
    except Exception as e:
        logger.error(f"Error fetching all health data: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching health data."}), 500

# Route to log new health data
@health_data_routes.route("/", methods=["POST"])
def log_health_data():
    """Log a new health data entry for a user."""
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        data_type = data.get("data_type")
        value = data.get("value")
        recorded_at = data.get("recorded_at", None)

        if not all([user_id, data_type, value]):
            return jsonify({"error": "Missing required fields."}), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        recorded_at = datetime.strptime(recorded_at, "%Y-%m-%d %H:%M:%S") if recorded_at else datetime.utcnow()

        new_health_data = HealthData(user_id=user_id, data_type=data_type, value=value, recorded_at=recorded_at)
        db.session.add(new_health_data)
        db.session.commit()

        return jsonify({
            "message": "Health data logged successfully.",
            "health_data": {
                "id": new_health_data.id,
                "user_id": new_health_data.user_id,
                "data_type": new_health_data.data_type,
                "value": new_health_data.value,
                "recorded_at": new_health_data.recorded_at.strftime("%Y-%m-%d %H:%M:%S")
            }
        }), 201
    except Exception as e:
        logger.error(f"Error logging health data: {str(e)}", exc_info=True)
        return jsonify({"error": "Error logging health data."}), 500

# Route to retrieve health data for a specific user
@health_data_routes.route("/user/<int:user_id>", methods=["GET"])
def get_health_data(user_id):
    """Retrieve health data records for a specific user."""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        health_records = HealthData.query.filter_by(user_id=user_id).all()
        if not health_records:
            return jsonify({"error": "No health data found for this user."}), 404

        return jsonify({"health_data": [
            {
                "id": record.id,
                "user_id": record.user_id,
                "data_type": record.data_type,
                "value": record.value,
                "recorded_at": record.recorded_at.strftime("%Y-%m-%d %H:%M:%S")
            } for record in health_records
        ]})
    except Exception as e:
        logger.error(f"Error fetching health data: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching health data."}), 500

# Route to generate AI-driven health insights
@health_data_routes.route("/user/<int:user_id>/insights", methods=["GET"])
def get_health_insights(user_id):
    """Generate AI-driven insights based on a user's health data."""
    try:
        verify_jwt_in_request(optional=True)
        authenticated_user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        if authenticated_user_id != user_id and not is_premium_user(user):
            return jsonify({
                "error": "Premium subscription required to view insights.",
                "requires_upgrade": True
            }), 403

        health_records = HealthData.query.filter_by(user_id=user_id).order_by(HealthData.recorded_at.desc()).limit(50).all()
        if not health_records:
            return jsonify({"message": "No health data available to analyze."}), 200

        health_data_text = "\n".join([
            f"{record.data_type}: {record.value} (recorded on {record.recorded_at.strftime('%Y-%m-%d %H:%M:%S')})"
            for record in health_records
        ])

        prompt = [
            {
                "role": "system",
                "content": "You are a medical assistant. Analyze the user's health data and provide a concise, natural language summary with actionable insights. Focus on trends, potential concerns, and simple recommendations. Respond as plain text, not JSON."
            },
            {
                "role": "user",
                "content": f"Analyze this health data:\n{health_data_text}"
            }
        ]

        insights = call_openai_api(prompt, max_tokens=500)
        return jsonify({
            "insights": insights,
            "health_data_count": len(health_records)
        }), 200
    except Exception as e:
        logger.error(f"Error generating health insights for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Error generating health insights."}), 500

# Route to delete a specific health data entry
@health_data_routes.route("/<int:data_id>", methods=["DELETE"])
def delete_health_data(data_id):
    """Delete a specific health data entry."""
    try:
        health_data = HealthData.query.get(data_id)
        if not health_data:
            return jsonify({"error": "Health data not found."}), 404

        db.session.delete(health_data)
        db.session.commit()

        return jsonify({"message": "Health data deleted successfully.", "deleted_id": data_id})
    except Exception as e:
        logger.error(f"Error deleting health data: {str(e)}", exc_info=True)
        return jsonify({"error": "Error deleting health data."}), 500