from flask import Blueprint, request, jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from backend.extensions import db
from backend.models import HealthData, User, UserTierEnum
import logging
from datetime import datetime
import openai
import os
import time
import json

# Logger setup
logger = logging.getLogger("health_data_routes")
health_data_routes = Blueprint("health_data_routes", __name__, url_prefix="/api/health-data")

# OpenAI setup
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set")

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_TOKENS = 1000
TEMPERATURE = 0.7

def is_premium_user(user):
    return getattr(user, "subscription_tier", UserTierEnum.FREE.value) in {
        UserTierEnum.PAID.value,
        UserTierEnum.ONE_TIME.value
    }

def call_openai_api(messages, retry_count=0):
    if retry_count >= MAX_RETRIES:
        logger.error("Max retries reached for OpenAI API call")
        return "Unable to generate insights at this time."
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",  # Changed from gpt-4-turbo to gpt-4o
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        content = response.choices[0].message.content.strip() if response.choices else ""
        logger.info(f"Raw OpenAI response: {content[:100]}...")  # Log first 100 chars
        
        if not content:
            logger.warning("Empty response from OpenAI")
            time.sleep(RETRY_DELAY)
            return call_openai_api(messages, retry_count + 1)
        return content
    except openai.RateLimitError:
        wait_time = min(10, (2 ** retry_count) * RETRY_DELAY)
        logger.warning(f"Rate limit hit. Retrying in {wait_time} seconds...")
        time.sleep(wait_time)
        return call_openai_api(messages, retry_count + 1)
    except openai.OpenAIError as e:
        logger.error(f"OpenAI API error: {str(e)}", exc_info=True)
        return "Error connecting to AI service."
    except Exception as e:
        logger.error(f"Unexpected error calling OpenAI API: {str(e)}", exc_info=True)
        return "An unexpected error occurred."

# Route for GET all health data
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
                "recorded_at": record.recorded_at.strftime("%Y-%m-%d %H:%M:%S")
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
        recorded_at = data.get("recorded_at", None)

        if not all([user_id, data_type, value]):
            return jsonify({"error": "Missing required fields."}), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        try:
            recorded_at = datetime.strptime(recorded_at, "%Y-%m-%d %H:%M:%S") if recorded_at else datetime.utcnow()
        except (TypeError, ValueError):
            recorded_at = datetime.utcnow()

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
                "recorded_at": record.recorded_at.strftime("%Y-%m-%d %H:%M:%S")
            } for record in health_records
        ]})
    except Exception as e:
        logger.error(f"Error fetching health data: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching health data."}), 500

# New route to generate AI-driven health insights
@health_data_routes.route("/user/<int:user_id>/insights", methods=["GET"])
def get_health_insights(user_id):
    try:
        # Verify JWT and get user
        verify_jwt_in_request(optional=True)
        authenticated_user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        # Restrict to authenticated user or premium users
        if authenticated_user_id != user_id and not is_premium_user(user):
            return jsonify({
                "error": "Premium subscription required to view insights.",
                "requires_upgrade": True
            }), 403

        # Fetch health data
        health_records = HealthData.query.filter_by(user_id=user_id).order_by(HealthData.recorded_at.desc()).limit(50).all()
        if not health_records:
            return jsonify({"message": "No health data available to analyze."}), 200

        # Format health data for OpenAI
        health_data_text = "\n".join([
            f"{record.data_type}: {record.value} (recorded on {record.recorded_at.strftime('%Y-%m-%d %H:%M:%S')})"
            for record in health_records
        ])

        # Prepare OpenAI prompt
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

        # Call OpenAI API
        insights = call_openai_api(prompt)

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