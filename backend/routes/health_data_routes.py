from flask import Blueprint, request, jsonify
from extensions import db
from models import HealthData, User
import logging
from datetime import datetime

# Logger setup
logger = logging.getLogger("health_data_routes")
health_data_routes = Blueprint("health_data_routes", __name__)

# Add this new route for GET all health data
@health_data_routes.route("/", methods=["GET"])
def get_all_health_data():
    try:
        health_records = HealthData.query.all()
        return jsonify({"health_data": [
            {
                "id": record.id,
                "user_id": record.user_id,
                "data_type": record.data_type,
                "value": record.value,
                "timestamp": record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            } for record in health_records
        ]})
    except Exception as e:
        logger.error(f"Error fetching all health data: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching health data."}), 500

# Route to log health data
@health_data_routes.route("/", methods=["POST"])
def log_health_data():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        data_type = data.get("data_type")
        value = data.get("value")
        timestamp = data.get("timestamp", None)

        if not all([user_id, data_type, value]):
            return jsonify({"error": "Missing required fields."}), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        try:
            timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S") if timestamp else datetime.utcnow()
        except (TypeError, ValueError):
            timestamp = datetime.utcnow()

        new_health_data = HealthData(user_id=user_id, data_type=data_type, value=value, timestamp=timestamp)
        db.session.add(new_health_data)
        db.session.commit()

        return jsonify({
            "message": "Health data logged successfully.",
            "health_data": {
                "id": new_health_data.id,
                "user_id": new_health_data.user_id,
                "data_type": new_health_data.data_type,
                "value": new_health_data.value,
                "timestamp": new_health_data.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            }
        }), 201
    except Exception as e:
        logger.error(f"Error logging health data: {str(e)}", exc_info=True)
        return jsonify({"error": "Error logging health data."}), 500

# Route to retrieve health data for a user
@health_data_routes.route("/user/<int:user_id>", methods=["GET"])
def get_health_data(user_id):
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
                "timestamp": record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            } for record in health_records
        ]})
    except Exception as e:
        logger.error(f"Error fetching health data: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching health data."}), 500

# Route to delete a specific health data entry
@health_data_routes.route("/<int:data_id>", methods=["DELETE"])
def delete_health_data(data_id):
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