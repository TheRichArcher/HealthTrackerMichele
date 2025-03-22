from flask import Blueprint, request, jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from backend.extensions import db
from backend.models import HealthData, User, UserTierEnum
import logging
from datetime import datetime
from backend.utils.openai_utils import call_openai_api

logger = logging.getLogger("health_data_routes")
health_data_routes = Blueprint("health_data_routes", __name__, url_prefix="/api/health-data")

class MedicalInfo(db.Model):
    __tablename__ = "medical_info"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    conditions = db.Column(db.Text)
    medications = db.Column(db.Text)
    allergies = db.Column(db.Text)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "age": self.age,
            "conditions": self.conditions,
            "medications": self.medications,
            "allergies": self.allergies,
            "recorded_at": self.recorded_at.strftime("%Y-%m-%d %H:%M:%S")
        }

def is_premium_user(user):
    return getattr(user, "subscription_tier", UserTierEnum.FREE) == UserTierEnum.PAID

@health_data_routes.route("/", methods=["GET"])
def get_all_health_data():
    try:
        # Optional JWT for broader access
        verify_jwt_in_request(optional=True)
        health_records = HealthData.query.all()
        return jsonify({"health_data": [record.to_dict() for record in health_records]}), 200
    except Exception as e:
        logger.error(f"Error fetching all health data: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching health data."}), 500

@health_data_routes.route("/", methods=["POST"])
def log_health_data():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        data_type = data.get("data_type")
        value = data.get("value")
        recorded_at = data.get("recorded_at")

        if not all([user_id, data_type, value]):
            return jsonify({"error": "Missing required fields: user_id, data_type, value."}), 400

        # Check authentication
        authenticated = True
        try:
            verify_jwt_in_request()
            if str(get_jwt_identity()) != str(user_id):
                return jsonify({"error": "Unauthorized access."}), 403
        except:
            authenticated = False

        user = User.query.get(user_id)
        if not user:
            if authenticated:
                return jsonify({"error": "User not found."}), 404
            logger.info(f"Health data (unauthenticated user {user_id}): {data}")
            return jsonify({"message": "Health data received but not stored."}), 200

        if not is_premium_user(user):
            logger.info(f"Health data (non-premium user {user_id}): {data}")
            return jsonify({"message": "Health data received but not stored."}), 200

        recorded_at = datetime.strptime(recorded_at, "%Y-%m-%d %H:%M:%S") if recorded_at else datetime.utcnow()
        new_health_data = HealthData(user_id=user_id, data_type=data_type, value=value, recorded_at=recorded_at)
        db.session.add(new_health_data)
        db.session.commit()

        return jsonify({
            "message": "Health data logged successfully.",
            "health_data": new_health_data.to_dict()
        }), 201
    except ValueError as e:
        logger.error(f"Invalid date format: {str(e)}", exc_info=True)
        return jsonify({"error": "Invalid recorded_at format. Use YYYY-MM-DD HH:MM:SS."}), 400
    except Exception as e:
        logger.error(f"Error logging health data: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "Error logging health data."}), 500

@health_data_routes.route("/user/<int:user_id>", methods=["GET"])
def get_health_data(user_id):
    try:
        verify_jwt_in_request()
        authenticated_user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        if str(user_id) != authenticated_user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        health_records = HealthData.query.filter_by(user_id=user_id).all()
        if not health_records:
            return jsonify({"message": "No health data found for this user."}), 200

        return jsonify({"health_data": [record.to_dict() for record in health_records]}), 200
    except Exception as e:
        logger.error(f"Error fetching health data for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching health data."}), 500

@health_data_routes.route("/user/<int:user_id>/insights", methods=["GET"])
def get_health_insights(user_id):
    try:
        verify_jwt_in_request()
        authenticated_user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        if str(user_id) != authenticated_user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        if not is_premium_user(user):
            return jsonify({"error": "Premium subscription required to view insights.", "requires_upgrade": True}), 403

        health_records = HealthData.query.filter_by(user_id=user_id).order_by(HealthData.recorded_at.desc()).limit(50).all()
        if not health_records:
            return jsonify({"message": "No health data available to analyze."}), 200

        health_data_text = "\n".join([
            f"{r.data_type}: {r.value} (recorded on {r.recorded_at.strftime('%Y-%m-%d %H:%M:%S')})"
            for r in health_records
        ])
        prompt = [
            {"role": "system", "content": "You are a medical assistant. Analyze the user's health data and provide a concise, natural language summary with actionable insights. Focus on trends, potential concerns, and simple recommendations. Respond as plain text."},
            {"role": "user", "content": f"Analyze this health data:\n{health_data_text}"}
        ]

        insights = call_openai_api(prompt, max_tokens=500)
        return jsonify({"insights": insights, "health_data_count": len(health_records)}), 200
    except Exception as e:
        logger.error(f"Error generating health insights for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Error generating health insights."}), 500

@health_data_routes.route("/<int:data_id>", methods=["DELETE"])
def delete_health_data(data_id):
    try:
        verify_jwt_in_request()
        authenticated_user_id = get_jwt_identity()
        health_data = HealthData.query.get(data_id)
        if not health_data:
            return jsonify({"error": "Health data not found."}), 404

        if str(health_data.user_id) != authenticated_user_id:
            return jsonify({"error": "Unauthorized access."}), 403

        db.session.delete(health_data)
        db.session.commit()
        return jsonify({"message": "Health data deleted successfully.", "deleted_id": data_id}), 200
    except Exception as e:
        logger.error(f"Error deleting health data {data_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Error deleting health data."}), 500

@health_data_routes.route("/medical-info", methods=["GET"])
def get_medical_info():
    try:
        query = request.args.get("query", "").strip()
        if not query:
            return jsonify({"error": "Query parameter is required."}), 400

        prompt = [
            {"role": "system", "content": "You are a medical knowledge assistant. Provide accurate, concise medical information based on the user's query. Respond as plain text."},
            {"role": "user", "content": f"Provide medical information about: {query}"}
        ]
        response = call_openai_api(prompt, max_tokens=500)
        return jsonify({"medical_info": response}), 200
    except Exception as e:
        logger.error(f"Error fetching medical info for query '{query}': {str(e)}", exc_info=True)
        return jsonify({"error": "Error retrieving medical information."}), 500

@health_data_routes.route("/medical-info", methods=["POST"])
def save_medical_info():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        authenticated = True
        try:
            verify_jwt_in_request()
            authenticated_user_id = get_jwt_identity()
            if str(user_id) != authenticated_user_id:
                return jsonify({"error": "Unauthorized access."}), 403
        except:
            authenticated = False

        if not user_id:
            return jsonify({"error": "User ID required."}), 400

        user = User.query.get(user_id)
        if not user:
            if authenticated:
                return jsonify({"error": "User not found."}), 404
            logger.info(f"Medical info (unauthenticated user {user_id}): {data}")
            return jsonify({"message": "Medical info received but not stored."}), 200

        if not is_premium_user(user):
            logger.info(f"Medical info (non-premium user {user_id}): {data}")
            return jsonify({"message": "Medical info received but not stored."}), 200

        medical_info = MedicalInfo(
            user_id=user_id,
            name=data.get("name", ""),
            age=int(data.get("age", 0)),
            conditions=data.get("conditions", ""),
            medications=data.get("medications", ""),
            allergies=data.get("allergies", "")
        )
        db.session.add(medical_info)
        db.session.commit()

        logger.info(f"Medical info saved for user {user_id}: {data}")
        return jsonify({"message": "Medical information saved successfully.", "medical_info": medical_info.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving medical info: {str(e)}", exc_info=True)
        return jsonify({"error": "Error saving medical information."}), 500