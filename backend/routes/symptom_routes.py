from flask import Blueprint, request, jsonify, current_app, session
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from backend.models import User, SymptomLog, Report, UserTierEnum, CareRecommendationEnum
from backend.extensions import db
from backend.utils.auth import generate_temp_user_id, token_required
from backend.utils.pdf_generator import generate_pdf_report
from backend.utils.openai_utils import call_openai_api
import openai_config
import openai
import os
import json
import logging
from datetime import datetime
import time
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

symptom_routes = Blueprint("symptom_routes", __name__, url_prefix="/api/symptoms")

# Note: OpenAI API settings (e.g., temperature, max tokens) are managed by call_openai_api in openai_utils.py
MIN_CONFIDENCE_THRESHOLD = 95  # Used to enforce confidence threshold for assessments

openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set")

logger = logging.getLogger(__name__)

class MockUser:
    subscription_tier = UserTierEnum.FREE.value

def is_premium_user(user):
    """Check if the user has a premium subscription tier or a valid temporary token."""
    # Check subscription tier for authenticated users
    if hasattr(user, "subscription_tier"):
        return user.subscription_tier in [UserTierEnum.PAID.value, UserTierEnum.ONE_TIME.value]
    
    # Check for temporary token for unauthenticated users
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        if user_id and isinstance(user_id, str) and user_id.startswith('temp_'):
            return True
    except Exception as e:
        logger.debug(f"Token verification failed in is_premium_user: {str(e)}")
    
    return False

def prepare_conversation_messages(symptom, conversation_history):
    """Prepare the conversation messages for OpenAI API."""
    custom_system_prompt = """You are Michele, an AI medical assistant designed to mimic a doctor's visit. Your goal is to understand the user's symptoms through conversation and provide insights only when highly confident.

    CRITICAL INSTRUCTIONS:
    1. ALWAYS return a valid JSON response with these exact fields:
       - "is_assessment": boolean (true only if confidence ≥ 95%)
       - "is_question": boolean (true if asking a follow-up question)
       - "possible_conditions": string (question text or condition name)
       - "confidence": number (0-100, null if no assessment)
       - "triage_level": string ("MILD", "MODERATE", "SEVERE", null if no assessment)
       - "care_recommendation": string (brief advice, null if no assessment)
       - "requires_upgrade": boolean (set by backend, default false)
    Optional:
       - "assessment_id": integer (if is_assessment=true)
       - "doctors_report": string (if requested)

    2. For assessments: Format conditions as "Medical Term (Common Name)".
    3. Ask ONE clear question at a time until ≥ 95% confidence.
    4. Rule out life-threatening conditions first (e.g., cardiovascular for chest discomfort).
    5. Be concise, empathetic, and precise."""
    
    messages = [{"role": "system", "content": custom_system_prompt}]
    for entry in conversation_history:
        role = "assistant" if entry.get("isBot", False) else "user"
        messages.append({"role": role, "content": entry.get("message", "")})
    if not conversation_history or conversation_history[-1].get("isBot", False):
        messages.append({"role": "user", "content": symptom})
    return messages

@symptom_routes.route("/count", methods=["GET"])
@token_required
def get_symptom_count(current_user=None):
    """Get the number of symptom logs for the current user."""
    if not current_user:
        return jsonify({"error": "Authentication required"}), 401

    user_id = current_user.get("user_id")
    if user_id and user_id.startswith('user_'):
        user_id = int(user_id.replace('user_', ''))  # Cast to integer
    symptom_count = SymptomLog.query.filter_by(user_id=user_id).count()
    return jsonify({"count": symptom_count}), 200

@symptom_routes.route("/analyze", methods=["POST"])
def analyze_symptoms():
    """Analyze user symptoms using OpenAI and manage conversation flow."""
    logger.info("Processing symptom analysis request")
    auth_header = request.headers.get("Authorization")
    user_id = None
    current_user = MockUser()

    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id and user_id.startswith('user_'):
                user_id = int(user_id.replace('user_', ''))  # Cast to integer if authenticated
            current_user = User.query.get(user_id) or MockUser()
        except Exception as e:
            logger.warning(f"Invalid token: {str(e)}")

    # Use temp ID if no authenticated user
    user_id = user_id if user_id is not None else generate_temp_user_id(request)

    # Check if the user must upgrade due to a previous serious assessment
    session_key = f"requires_upgrade_{user_id}"
    if session.get(session_key, False) and not is_premium_user(current_user):
        return jsonify({
            "error": "Upgrade required to continue due to a previous serious assessment",
            "requires_upgrade": True
        }), 403

    data = request.get_json() or {}
    symptom = data.get("symptom", "").strip()
    conversation_history = data.get("conversation_history", [])

    if not symptom or not isinstance(symptom, str):
        return jsonify({"response": "Please describe your symptoms.", "isBot": True, "conversation_history": conversation_history}), 400
    if not isinstance(conversation_history, list):
        return jsonify({"error": "Conversation history must be a list."}), 400

    messages = prepare_conversation_messages(symptom, conversation_history)
    try:
        raw_response = call_openai_api(messages, response_format={"type": "json_object"})
        result = openai_config.clean_ai_response(raw_response)
        
        if result.get("is_assessment", False) and result.get("confidence", 0) < MIN_CONFIDENCE_THRESHOLD:
            result = {
                "is_assessment": False,
                "is_question": True,
                "possible_conditions": "I need more details—can you describe any other symptoms?",
                "confidence": None,
                "triage_level": None,
                "care_recommendation": None,
                "requires_upgrade": False
            }

        assessment_id = None
        if result.get("is_assessment", False) and isinstance(user_id, int):  # Only save for authenticated users
            notes = {
                "response": result,
                "condition_common": result.get("possible_conditions", "").split("(")[0].strip() if "(" in result.get("possible_conditions", "") else result.get("possible_conditions", "Unknown"),
                "condition_medical": result.get("possible_conditions", "").split("(")[1].split(")")[0].strip() if "(" in result.get("possible_conditions", "") and ")" in result.get("possible_conditions", "") else "N/A",
                "confidence": result.get("confidence", 0),
                "triage_level": result.get("triage_level", "MODERATE"),
                "care_recommendation": result.get("care_recommendation", "Consult a healthcare provider")
            }
            symptom_log = SymptomLog(
                user_id=user_id,
                symptom_name=symptom,
                notes=json.dumps(notes)
            )
            db.session.add(symptom_log)
            db.session.commit()
            assessment_id = symptom_log.id
            result["assessment_id"] = assessment_id

        if not is_premium_user(current_user) and result.get("is_assessment", False):
            triage_level = result.get("triage_level", "").upper()
            if triage_level in ["MODERATE", "SEVERE"]:
                result["requires_upgrade"] = True
                session[session_key] = True  # Store the upgrade requirement in the session

        response_data = {
            "is_assessment": result.get("is_assessment", False),
            "next_question": result.get("possible_conditions") if result.get("is_question", False) else None,
            "possible_conditions": result.get("possible_conditions", ""),
            "confidence": result.get("confidence", None),
            "triage_level": result.get("triage_level", None),
            "care_recommendation": result.get("care_recommendation", None),
            "requires_upgrade": result.get("requires_upgrade", False),
            "assessment_id": assessment_id
        }

        # Format a user-friendly message for the conversation history
        history_message = response_data["next_question"]
        if not history_message:  # If no next_question, format the assessment as a string
            history_message = f"I've identified {response_data['possible_conditions']} as a possible condition.\nConfidence: {response_data['confidence']}%\nSeverity: {response_data['triage_level']}\nRecommendation: {response_data['care_recommendation']}"

        conversation_history.append({"message": history_message, "isBot": True})
        return jsonify({"response": response_data, "isBot": True, "conversation_history": conversation_history}), 200
    except Exception as e:
        logger.error(f"Error in analyze_symptoms: {str(e)}", exc_info=True)
        return jsonify({"response": "Error processing your request.", "isBot": True, "conversation_history": conversation_history}), 500

@symptom_routes.route("/reset", methods=["POST"])
def reset_conversation():
    """Reset the conversation state."""
    logger.info("Processing conversation reset request")
    auth_header = request.headers.get("Authorization")
    user_id = None
    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id and user_id.startswith('user_'):
                user_id = int(user_id.replace('user_', ''))  # Cast to integer if authenticated
        except Exception as e:
            logger.warning(f"Invalid token: {str(e)}")

    welcome_message = {
        "sender": "bot",
        "text": "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health.\n\nYou can start by describing your symptoms like:\n• \"I've had a headache for two days\"\n• \"My throat is sore and I have a fever\"\n• \"I have a rash on my arm that's itchy\"",
        "confidence": None,
        "careRecommendation": None,
        "isAssessment": False,
        "isUpgradeOptions": False
    }

    return jsonify({
        "message": "Conversation reset successfully",
        "response": welcome_message["text"],
        "isBot": True,
        "conversation_history": []
    }), 200

@symptom_routes.route("/history", methods=["GET"])
@token_required
def get_symptom_history(current_user=None):
    """Retrieve symptom history for the authenticated user."""
    if not current_user:
        return jsonify({"error": "Authentication required"}), 401

    user_id = current_user.get("user_id")
    if user_id and user_id.startswith('user_'):
        user_id = int(user_id.replace('user_', ''))  # Cast to integer
    user = User.query.get(user_id)
    if not user or user.subscription_tier != UserTierEnum.PAID.value:
        return jsonify({"error": "Premium subscription required", "requires_upgrade": True}), 403

    symptoms = SymptomLog.query.filter_by(user_id=user_id).order_by(SymptomLog.timestamp.desc()).all()
    history = [{
        "id": s.id,
        "symptom": s.symptom_name,
        "notes": json.loads(s.notes) if s.notes and s.notes.startswith('{') else s.notes,
        "timestamp": s.timestamp.isoformat()
    } for s in symptoms]
    return jsonify({"history": history}), 200

@symptom_routes.route("/doctor-report", methods=["POST"])
def generate_doctor_report():
    """Generate a doctor's report for premium users."""
    logger.info("Processing doctor's report request")
    auth_header = request.headers.get("Authorization")
    user_id = None
    current_user = MockUser()

    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id and user_id.startswith('user_'):
                user_id = int(user_id.replace('user_', ''))  # Cast to integer if authenticated
            current_user = User.query.get(user_id) or MockUser()
        except Exception as e:
            logger.warning(f"Invalid token: {str(e)}")

    if not is_premium_user(current_user):
        return jsonify({"error": "Premium access required", "requires_upgrade": True}), 403

    data = request.get_json() or {}
    symptom = data.get("symptom", "")
    conversation_history = data.get("conversation_history", [])

    if not symptom:
        return jsonify({"error": "Symptom is required."}), 400

    messages = prepare_conversation_messages(symptom, conversation_history)
    messages[-1]["content"] += " Generate a comprehensive medical report suitable for healthcare providers."
    
    try:
        raw_response = call_openai_api(messages, response_format={"type": "json_object"})
        result = openai_config.clean_ai_response(raw_response)
        doctor_report = result.get("doctors_report") or f"""
        MEDICAL CONSULTATION REPORT
        Date: {datetime.utcnow().strftime("%Y-%m-%d")}
        PATIENT SYMPTOMS: {symptom}
        ASSESSMENT: {result.get("possible_conditions", "Unknown")}
        CONFIDENCE: {result.get("confidence", "Unknown")}%
        CARE RECOMMENDATION: {result.get("care_recommendation", "Consult a healthcare provider")}
        NOTES: For a definitive diagnosis, consult a healthcare provider.
        """
        # Validate report_data to prevent malformed inputs
        confidence = result.get("confidence", 0)
        if isinstance(confidence, str):
            confidence = float(confidence.rstrip('%')) if '%' in confidence else float(confidence)
        report_data = {
            "user_id": user_id if user_id is not None else generate_temp_user_id(request),
            "timestamp": datetime.utcnow().isoformat(),
            "symptom": symptom,
            "condition_common": result.get("possible_conditions", "Unknown").split("(")[0].strip() if "(" in result.get("possible_conditions", "") else result.get("possible_conditions", "Unknown"),
            "condition_medical": result.get("possible_conditions", "").split("(")[1].split(")")[0].strip() if "(" in result.get("possible_conditions", "") and ")" in result.get("possible_conditions", "") else "N/A",
            "confidence": confidence,
            "triage_level": result.get("triage_level", "MODERATE"),
            "care_recommendation": result.get("care_recommendation", "Consult a healthcare provider")
        }
        report_url = generate_pdf_report(report_data)

        if user_id and isinstance(user_id, int):  # Only save for authenticated users
            notes = {
                "response": result,
                "condition_common": report_data["condition_common"],
                "condition_medical": report_data["condition_medical"],
                "confidence": report_data["confidence"],
                "triage_level": report_data["triage_level"],
                "care_recommendation": report_data["care_recommendation"]
            }
            symptom_log = SymptomLog(
                user_id=user_id,
                symptom_name=symptom,
                notes=json.dumps(notes)
            )
            db.session.add(symptom_log)
            db.session.commit()
            report = Report(
                user_id=user_id,
                title=f"Doctor's Report - {datetime.utcnow().strftime('%Y-%m-%d')}",
                content=json.dumps(report_data),
                care_recommendation=CareRecommendationEnum.SEE_DOCTOR,
                created_at=datetime.utcnow()
            )
            db.session.add(report)
            db.session.commit()

        return jsonify({"doctors_report": doctor_report, "report_url": report_url, "success": True}), 200
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to generate report", "success": False}), 500

@symptom_routes.route("/<int:symptom_id>", methods=["GET"])
@token_required
def get_symptom_log(symptom_id, current_user=None):
    """Retrieve a specific symptom log by ID."""
    if not current_user:
        return jsonify({"error": "Authentication required"}), 401

    user_id = current_user.get("user_id")
    if user_id and user_id.startswith('user_'):
        user_id = int(user_id.replace('user_', ''))  # Cast to integer
    symptom_log = SymptomLog.query.filter_by(id=symptom_id, user_id=user_id).first()
    if not symptom_log:
        return jsonify({"error": "Symptom log not found or unauthorized"}), 404

    return jsonify({
        "id": symptom_log.id,
        "symptom": symptom_log.symptom_name,
        "notes": json.loads(symptom_log.notes) if symptom_log.notes and symptom_log.notes.startswith('{') else symptom_log.notes,
        "timestamp": symptom_log.timestamp.isoformat()
    }), 200

@symptom_routes.route("/", methods=["POST"])
@token_required
def log_symptom(current_user=None):
    """Log a new symptom for the authenticated user."""
    if not current_user:
        return jsonify({"error": "Authentication required"}), 401

    user_id = current_user.get("user_id")
    if user_id and user_id.startswith('user_'):
        user_id = int(user_id.replace('user_', ''))  # Cast to integer

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    symptom = data.get("symptom", "").strip()
    notes = data.get("notes", "").strip()
    intensity = data.get("intensity")
    respiratory_rate = data.get("respiratory_rate")
    oxygen_saturation = data.get("oxygen_saturation")
    waist_circumference = data.get("waist_circumference")

    if not symptom:
        return jsonify({"error": "Symptom is required"}), 400

    try:
        symptom_log = SymptomLog(
            user_id=user_id,
            symptom_name=symptom,
            notes=notes,
            intensity=intensity,
            respiratory_rate=respiratory_rate,
            oxygen_saturation=oxygen_saturation,
            waist_circumference=waist_circumference
        )
        db.session.add(symptom_log)
        db.session.commit()

        return jsonify({
            "message": "Symptom logged successfully",
            "symptom_log": {
                "id": symptom_log.id,
                "symptom": symptom_log.symptom_name,
                "notes": symptom_log.notes,
                "intensity": symptom_log.intensity,
                "respiratory_rate": symptom_log.respiratory_rate,
                "oxygen_saturation": symptom_log.oxygen_saturation,
                "waist_circumference": symptom_log.waist_circumference,
                "timestamp": symptom_log.timestamp.isoformat()
            }
        }), 201
    except Exception as e:
        logger.error(f"Error logging symptom: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "Failed to log symptom"}), 500

@symptom_routes.route("/delete/<int:symptom_id>", methods=["DELETE"])
@token_required
def delete_symptom_log(symptom_id, current_user=None):
    """Delete a specific symptom log by ID."""
    if not current_user:
        return jsonify({"error": "Authentication required"}), 401

    user_id = current_user.get("user_id")
    if user_id and user_id.startswith('user_'):
        user_id = int(user_id.replace('user_', ''))  # Cast to integer
    symptom_log = SymptomLog.query.filter_by(id=symptom_id, user_id=user_id).first()
    if not symptom_log:
        return jsonify({"error": "Symptom log not found or unauthorized"}), 404

    try:
        db.session.delete(symptom_log)
        db.session.commit()
        return jsonify({"message": "Symptom log deleted successfully", "deleted_id": symptom_id}), 200
    except Exception as e:
        logger.error(f"Error deleting symptom log: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "Failed to delete symptom log"}), 500