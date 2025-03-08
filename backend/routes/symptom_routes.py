from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from backend.models import User, Symptom, Report, UserTierEnum, CareRecommendationEnum
from backend.extensions import db
from backend.openai_config import clean_ai_response  # Import the updated config
import openai
import os
import json
import logging
from datetime import datetime
import time

# Blueprint setup
symptom_routes = Blueprint("symptom_routes", __name__)

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_FREE_MESSAGES = 15
MIN_CONFIDENCE_THRESHOLD = 85  # Aligned with openai_config.py
EMPTY_RESPONSE_RETRIES = 2
MAX_TOKENS = 1500
TEMPERATURE = 0.7

# Configure OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set")

# Logger setup
logger = logging.getLogger(__name__)

# Mock user for unauthenticated requests
class MockUser:
    subscription_tier = UserTierEnum.FREE.value  # Use string value for consistency

# Utility functions
def is_premium_user(user):
    """Check if the user has premium access."""
    return getattr(user, "subscription_tier", UserTierEnum.FREE.value) in {
        UserTierEnum.PAID.value,
        UserTierEnum.ONE_TIME.value
    }

def prepare_conversation_messages(symptom, conversation_history):
    """Prepare messages for OpenAI API with system prompt and conversation context."""
    system_prompt = f"""You are Michele, an AI medical assistant. Always return a valid JSON response with:
- "is_assessment": boolean (true if ≥{MIN_CONFIDENCE_THRESHOLD}% confidence diagnosis)
- "is_question": boolean (true if asking a follow-up question)
- "possible_conditions": string (question or assessment text)
- "confidence": number (0-100)
- "triage_level": string ("MILD", "MODERATE", "SEVERE")
- "care_recommendation": string (brief advice)
- "requires_upgrade": boolean (true for free-tier detailed assessments)

For assessments (is_assessment=true), include:
- "assessment": {{"conditions": [{{"name": "Medical Term (Common Name)", "confidence": number, "is_chronic": boolean}}], "triage_level": string, "care_recommendation": string}}

Ask 5+ questions before diagnosing. Avoid diagnosis if confidence <{MIN_CONFIDENCE_THRESHOLD}%. Use 'Medical Term (Common Name)' for conditions."""

    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    for entry in conversation_history:
        role = "assistant" if entry.get("isBot", False) else "user"
        content = entry.get("message", "")
        messages.append({"role": role, "content": content})

    # Add current symptom if not already in conversation or if last message is from bot
    if not conversation_history or conversation_history[-1].get("isBot", False):
        messages.append({"role": "user", "content": symptom})

    return messages

def call_openai_api(messages, retry_count=0):
    """Call OpenAI API with retry logic for rate limits and empty responses."""
    if retry_count >= MAX_RETRIES:
        logger.error("Max retries reached for OpenAI API call")
        raise RuntimeError("Failed to get response from OpenAI after multiple attempts")

    try:
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        logger.debug(f"OpenAI raw response: {response}")

        # Handle empty or invalid response
        if not response.choices or not response.choices[0].message or not response.choices[0].message.content.strip():
            logger.warning(f"Empty or malformed response from OpenAI (Attempt {retry_count + 1}/{MAX_RETRIES})")
            if retry_count + 1 < EMPTY_RESPONSE_RETRIES:
                time.sleep(RETRY_DELAY)
                return call_openai_api(messages, retry_count + 1)
            else:
                logger.info("Falling back to gpt-3.5-turbo")
                response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS
                )
                if not response.choices or not response.choices[0].message or not response.choices[0].message.content.strip():
                    logger.error("Fallback to gpt-3.5-turbo failed")
                    raise ValueError("AI service did not return a valid response")
        return response.choices[0].message.content

    except openai.RateLimitError:
        wait_time = (2 ** retry_count) * RETRY_DELAY
        logger.warning(f"Rate limit hit. Retrying in {wait_time} seconds...")
        time.sleep(wait_time)
        return call_openai_api(messages, retry_count + 1)
    except openai.OpenAIError as e:
        logger.error(f"OpenAI API error: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error calling OpenAI API: {str(e)}", exc_info=True)
        raise

def save_symptom_interaction(user_id, symptom_text, ai_response, care_recommendation, confidence, is_assessment):
    """Save symptom interaction and report to the database."""
    try:
        if isinstance(ai_response, dict):
            response_text = json.dumps(ai_response)
        else:
            response_text = ai_response

        new_symptom = Symptom(
            user_id=user_id,
            description=symptom_text,
            response=response_text,
            created_at=datetime.utcnow()
        )
        db.session.add(new_symptom)
        db.session.commit()

        if is_assessment:
            care_recommendation_enum = CareRecommendationEnum.SEE_DOCTOR  # Default
            if "manage at home" in care_recommendation.lower():
                care_recommendation_enum = CareRecommendationEnum.HOME_CARE
            elif "urgent" in care_recommendation.lower() or "emergency" in care_recommendation.lower():
                care_recommendation_enum = CareRecommendationEnum.URGENT_CARE

            report_content = {
                "assessment": ai_response.get("possible_conditions", ""),
                "care_recommendation": care_recommendation,
                "confidence": confidence,
                "doctors_report": ai_response.get("doctors_report", "")
            }

            new_report = Report(
                user_id=user_id,
                symptom_id=new_symptom.id,
                title=f"Assessment Report - {datetime.utcnow().strftime('%Y-%m-%d')}",
                content=json.dumps(report_content),
                care_recommendation=care_recommendation_enum,
                created_at=datetime.utcnow()
            )
            db.session.add(new_report)
            db.session.commit()
            logger.info(f"Created report for assessment with ID: {new_report.id} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving symptom interaction for user {user_id}: {str(e)}", exc_info=True)
        db.session.rollback()
        return False

# Routes
@symptom_routes.route("/analyze", methods=["POST"])
def analyze_symptoms():
    """Analyze user symptoms with tiered access and conversation history."""
    is_production = current_app.config.get("ENV") == "production" if current_app else False
    logger.info("Processing symptom analysis request")

    # Authentication
    auth_header = request.headers.get("Authorization")
    user_id = None
    current_user = MockUser()

    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id:
                current_user = User.query.get(user_id) or MockUser()
                if not is_production:
                    logger.info(f"Authenticated user {user_id}, tier: {current_user.subscription_tier}")
        except Exception as e:
            logger.warning(f"Invalid token for user: {str(e)}")

    # Parse request data
    data = request.get_json() or {}
    symptom = data.get("symptom", "").strip()
    conversation_history = data.get("conversation_history", [])
    context_notes = data.get("context_notes", "")
    one_time_report = data.get("one_time_report", False)
    reset = data.get("reset", False)

    # Input validation
    if not symptom or not isinstance(symptom, str):
        logger.warning("Invalid or missing symptom input")
        return jsonify({
            "possible_conditions": "Please describe your symptoms.",
            "care_recommendation": "Consider seeing a doctor soon.",
            "is_question": True,
            "requires_upgrade": False
        }), 400

    if not isinstance(conversation_history, list):
        logger.warning("Invalid conversation_history format")
        return jsonify({"error": "Conversation history must be a list.", "requires_upgrade": False}), 400

    for entry in conversation_history:
        if not isinstance(entry, dict) or "message" not in entry or "isBot" not in entry:
            logger.warning(f"Invalid conversation history entry: {entry}")
            return jsonify({"error": "Each conversation history entry must have 'message' and 'isBot' fields.", "requires_upgrade": False}), 400
        if not isinstance(entry["message"], str) or not isinstance(entry["isBot"], bool):
            logger.warning(f"Invalid types in conversation history entry: {entry}")
            return jsonify({"error": "Conversation history entries must have a string 'message' and boolean 'isBot'.", "requires_upgrade": False}), 400

    # Handle reset
    if reset:
        user_messages = sum(1 for msg in conversation_history if not msg.get("isBot", False))
        if not is_premium_user(current_user) and user_messages >= MAX_FREE_MESSAGES:
            return jsonify({
                "message": "Free users cannot reset after reaching the message limit.",
                "requires_upgrade": True,
                "upgrade_options": [
                    {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"},
                    {"type": "one_time", "name": "Doctor's Report", "price": 4.99}
                ]
            }), 403
        return jsonify({
            "message": "Conversation reset successfully",
            "possible_conditions": "Hello! I'm your AI medical assistant. Please describe your symptoms.",
            "is_assessment": False,
            "is_greeting": True,
            "requires_upgrade": False
        }), 200

    # Enforce free tier message limit
    if not is_premium_user(current_user):
        user_messages = sum(1 for msg in conversation_history if not msg.get("isBot", False))
        if user_messages >= MAX_FREE_MESSAGES:
            return jsonify({
                "message": "Free message limit reached. Upgrade or reset to continue.",
                "requires_upgrade": True,
                "can_reset": True,
                "upgrade_options": [
                    {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"},
                    {"type": "one_time", "name": "Doctor's Report", "price": 4.99}
                ]
            }), 200

    # Process with OpenAI
    messages = prepare_conversation_messages(symptom, conversation_history)
    try:
        response_text = call_openai_api(messages)
        result = clean_ai_response(response_text, current_user, conversation_history, symptom)

        # Save interaction if authenticated
        if user_id and result.get("is_assessment", False):
            save_symptom_interaction(
                user_id,
                symptom,
                result,
                result.get("care_recommendation", ""),
                result.get("confidence", 0),
                result.get("is_assessment", False)
            )

        return jsonify(result), 200

    except (ValueError, RuntimeError) as e:
        logger.error(f"AI processing failed: {str(e)}")
        return jsonify({
            "error": "AI service unavailable. Please try again later.",
            "requires_upgrade": False
        }), 503
    except Exception as e:
        logger.error(f"Unexpected error in symptom analysis: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Error processing your request. Please try again.",
            "possible_conditions": "I apologize, but I'm having trouble processing your request right now. Please try again or seek medical attention if concerned.",
            "care_recommendation": "Consider seeing a doctor soon.",
            "requires_upgrade": False
        }), 500

@symptom_routes.route("/history", methods=["GET"])
def get_symptom_history():
    """Retrieve symptom history for authenticated premium users."""
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user or user.subscription_tier != UserTierEnum.PAID.value:
            return jsonify({
                "error": "Premium subscription required",
                "requires_upgrade": True,
                "upgrade_options": [{"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"}]
            }), 403

        symptoms = Symptom.query.filter_by(user_id=user_id).order_by(Symptom.created_at.desc()).all()
        result = []
        for symptom in symptoms:
            try:
                response_data = json.loads(symptom.response) if isinstance(symptom.response, str) else symptom.response
                report = Report.query.filter_by(symptom_id=symptom.id).first()
                entry = {
                    "id": symptom.id,
                    "description": symptom.description,
                    "created_at": symptom.created_at.isoformat(),
                    "response": response_data
                }
                if report:
                    report_content = json.loads(report.content) if isinstance(report.content, str) else report.content
                    entry["report"] = report_content
                result.append(entry)
            except (json.JSONDecodeError, Exception) as e:
                logger.error(f"Error processing symptom {symptom.id}: {str(e)}")
                result.append({
                    "id": symptom.id,
                    "description": symptom.description,
                    "created_at": symptom.created_at.isoformat(),
                    "error": "Failed to process response"
                })
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error retrieving symptom history for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@symptom_routes.route("/doctor-report", methods=["POST"])
def generate_doctor_report():
    """Generate a one-time doctor's report for premium users."""
    logger.info("Processing doctor's report request")
    auth_header = request.headers.get("Authorization")
    user_id = None
    current_user = MockUser()

    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id:
                current_user = User.query.get(user_id) or MockUser()
        except Exception as e:
            logger.warning(f"Invalid token: {str(e)}")

    if not is_premium_user(current_user):
        return jsonify({
            "error": "Premium access required for doctor's report",
            "requires_upgrade": True,
            "upgrade_options": [
                {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"},
                {"type": "one_time", "name": "Doctor's Report", "price": 4.99}
            ]
        }), 403

    data = request.get_json() or {}
    symptom = data.get("symptom", "")
    conversation_history = data.get("conversation_history", [])

    if not symptom or not isinstance(symptom, str):
        logger.warning("Invalid or missing symptom for doctor's report")
        return jsonify({"error": "Symptom is required.", "requires_upgrade": False}), 400

    messages = prepare_conversation_messages(symptom, conversation_history)
    messages[-1]["content"] += " Generate a comprehensive medical report suitable for healthcare providers."

    try:
        response_text = call_openai_api(messages)
        result = clean_ai_response(response_text, current_user, conversation_history, symptom)

        doctor_report = result.get("doctors_report", "")
        if not doctor_report:
            doctor_report = f"""
MEDICAL CONSULTATION REPORT
Date: {datetime.utcnow().strftime("%Y-%m-%d")}

PATIENT SYMPTOMS:
{symptom}

ASSESSMENT:
{result.get("possible_conditions", "Unable to determine specific condition")}

CONFIDENCE LEVEL: {result.get("confidence", "Unknown")}%

CARE RECOMMENDATION:
{result.get("care_recommendation", "Consider consulting with a healthcare provider")}

NOTES:
This report was generated based on the symptoms provided. For a definitive diagnosis, consult a healthcare provider.
"""

        if user_id:
            symptom_record = Symptom.query.filter_by(user_id=user_id, description=symptom).order_by(Symptom.created_at.desc()).first()
            if not symptom_record:
                symptom_record = Symptom(
                    user_id=user_id,
                    description=symptom,
                    response="One-time doctor's report generated",
                    created_at=datetime.utcnow()
                )
                db.session.add(symptom_record)
                db.session.commit()

            report_content = {
                "doctors_report": doctor_report,
                "care_recommendation": result.get("care_recommendation", ""),
                "generated_at": datetime.utcnow().isoformat(),
                "one_time_purchase": True
            }

            existing_report = Report.query.filter_by(symptom_id=symptom_record.id).first()
            if existing_report:
                existing_report.content = json.dumps(report_content)
                existing_report.created_at = datetime.utcnow()
            else:
                new_report = Report(
                    user_id=user_id,
                    symptom_id=symptom_record.id,
                    title=f"Doctor's Report - {datetime.utcnow().strftime('%Y-%m-%d')}",
                    content=json.dumps(report_content),
                    care_recommendation=CareRecommendationEnum.SEE_DOCTOR,
                    created_at=datetime.utcnow()
                )
                db.session.add(new_report)
            db.session.commit()

        return jsonify({
            "doctors_report": doctor_report,
            "care_recommendation": result.get("care_recommendation", "Consider seeing a doctor soon."),
            "success": True
        }), 200

    except Exception as e:
        logger.error(f"Error generating doctor's report for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to generate doctor's report", "success": False}), 500

@symptom_routes.route("/reset", methods=["POST"])
def reset_conversation():
    """Reset the conversation history with tiered access limits."""
    logger.info("Processing conversation reset request")
    auth_header = request.headers.get("Authorization")
    user_id = None
    current_user = MockUser()

    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id:
                current_user = User.query.get(user_id) or MockUser()
        except Exception as e:
            logger.warning(f"Invalid token: {str(e)}")

    data = request.get_json() or {}
    conversation_history = data.get("conversation_history", [])

    user_messages = sum(1 for msg in conversation_history if not msg.get("isBot", False))
    if not is_premium_user(current_user) and user_messages >= MAX_FREE_MESSAGES:
        return jsonify({
            "message": "Free users cannot reset after reaching the message limit.",
            "requires_upgrade": True,
            "upgrade_options": [
                {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"},
                {"type": "one_time", "name": "Doctor's Report", "price": 4.99}
            ]
        }), 403

    return jsonify({
        "message": "Conversation reset successfully",
        "possible_conditions": "Hello! I'm your AI medical assistant. Please describe your symptoms.",
        "is_assessment": False,
        "is_greeting": True,
        "requires_upgrade": False
    }), 200

@symptom_routes.route("/debug", methods=["GET"])
def debug_route():
    """Debug endpoint to test symptom analysis."""
    logger.info("Processing debug request")
    auth_header = request.headers.get("Authorization")
    user_id = None
    current_user = MockUser()

    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id:
                current_user = User.query.get(user_id) or MockUser()
        except Exception:
            pass

    test_symptom = "My eye is red, itchy, and has a crusty discharge"
    test_history = [
        {"isBot": False, "message": test_symptom},
        {"isBot": True, "message": "How long have you been experiencing these symptoms?"},
        {"isBot": False, "message": "About 2 days now"}
    ]

    try:
        messages = prepare_conversation_messages(test_symptom, test_history)
        response_text = call_openai_api(messages)
        result = clean_ai_response(response_text, current_user, test_history, test_symptom)
        logger.info(f"Debug result for user {user_id or 'Anonymous'}: {result}")
        return jsonify({
            "symptom": test_symptom,
            "processed_result": result,
            "requires_upgrade": result.get("requires_upgrade", False),
            "user_tier": current_user.subscription_tier
        }), 200
    except Exception as e:
        logger.error(f"Debug error for user {user_id or 'Anonymous'}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500