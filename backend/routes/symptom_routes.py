from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from backend.models import User, SymptomLog, Report, UserTierEnum, CareRecommendationEnum
from backend.extensions import db
from backend.utils.auth import generate_temp_user_id, token_required
from backend.utils.pdf_generator import generate_pdf_report
import openai
import os
import json
import logging
from datetime import datetime
import time
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

symptom_routes = Blueprint("symptom_routes", __name__, url_prefix="/api/symptoms")

MAX_RETRIES = 3
RETRY_DELAY = 2
MIN_CONFIDENCE_THRESHOLD = 95
MAX_TOKENS = 1500
TEMPERATURE = 0.7

openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set")

logger = logging.getLogger(__name__)

class MockUser:
    subscription_tier = UserTierEnum.FREE.value

def is_premium_user(user):
    return getattr(user, "subscription_tier", UserTierEnum.FREE.value) in {
        UserTierEnum.PAID.value,
        UserTierEnum.ONE_TIME.value
    }

def prepare_conversation_messages(symptom, conversation_history):
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

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(openai.OpenAIError))
def call_openai_api(messages):
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        content = response.choices[0].message.content.strip()
        return json.loads(content)
    except openai.OpenAIError as e:
        logger.error(f"OpenAI API error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in OpenAI call: {str(e)}")
        raise

@symptom_routes.route("/analyze", methods=["POST"])
def analyze_symptoms():
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

    user_id = user_id or generate_temp_user_id(request)  # Keep temp IDs as strings

    data = request.get_json() or {}
    symptom = data.get("symptom", "").strip()
    conversation_history = data.get("conversation_history", [])

    if not symptom or not isinstance(symptom, str):
        return jsonify({"response": "Please describe your symptoms.", "isBot": True, "conversation_history": conversation_history}), 400
    if not isinstance(conversation_history, list):
        return jsonify({"error": "Conversation history must be a list."}), 400

    messages = prepare_conversation_messages(symptom, conversation_history)
    try:
        result = call_openai_api(messages)
        
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
        if result.get("is_assessment", False):
            symptom_log = SymptomLog(
                user_id=user_id,
                symptom=symptom,
                response=json.dumps(result),
                condition_common=result.get("possible_conditions", "").split("(")[0].strip() if "(" in result.get("possible_conditions", "") else result.get("possible_conditions", "Unknown"),
                condition_medical=result.get("possible_conditions", "").split("(")[1].split(")")[0].strip() if "(" in result.get("possible_conditions", "") and ")" in result.get("possible_conditions", "") else "N/A",
                confidence=result.get("confidence", 0),
                triage_level=result.get("triage_level", "MODERATE"),
                care_recommendation=result.get("care_recommendation", "Consult a healthcare provider"),
                created_at=datetime.utcnow()
            )
            db.session.add(symptom_log)
            db.session.commit()
            assessment_id = symptom_log.id
            result["assessment_id"] = assessment_id

        if not is_premium_user(current_user) and result.get("is_assessment", False):
            triage_level = result.get("triage_level", "").upper()
            if triage_level in ["MODERATE", "SEVERE"]:
                result["requires_upgrade"] = True

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

        conversation_history.append({"message": response_data["next_question"] or json.dumps(response_data), "isBot": True})
        return jsonify({"response": response_data, "isBot": True, "conversation_history": conversation_history}), 200
    except Exception as e:
        logger.error(f"Error in analyze_symptoms: {str(e)}")
        return jsonify({"response": "Error processing your request.", "isBot": True, "conversation_history": conversation_history}), 500

@symptom_routes.route("/reset", methods=["POST"])
def reset_conversation():
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

    return jsonify({
        "message": "Conversation reset successfully",
        "response": "Hi, I'm Michele—your AI medical assistant. Describe your symptoms like: 'I've had a headache for two days'.",
        "isBot": True,
        "conversation_history": []
    }), 200

@symptom_routes.route("/history", methods=["GET"])
@token_required
def get_symptom_history(current_user=None):
    if not current_user:
        return jsonify({"error": "Authentication required"}), 401

    user_id = current_user.get("user_id")
    if user_id and user_id.startswith('user_'):
        user_id = int(user_id.replace('user_', ''))  # Cast to integer
    user = User.query.get(user_id)
    if not user or user.subscription_tier != UserTierEnum.PAID.value:
        return jsonify({"error": "Premium subscription required", "requires_upgrade": True}), 403

    symptoms = SymptomLog.query.filter_by(user_id=user_id).order_by(SymptomLog.created_at.desc()).all()
    history = [{
        "id": s.id,
        "symptom": s.symptom,
        "response": json.loads(s.response),
        "confidence": s.confidence,
        "condition_common": s.condition_common,
        "condition_medical": s.condition_medical,
        "triage_level": s.triage_level,
        "care_recommendation": s.care_recommendation,
        "created_at": s.created_at.isoformat()
    } for s in symptoms]
    return jsonify({"history": history}), 200

@symptom_routes.route("/doctor-report", methods=["POST"])
def generate_doctor_report():
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
        result = call_openai_api(messages)
        doctor_report = result.get("doctors_report") or f"""
        MEDICAL CONSULTATION REPORT
        Date: {datetime.utcnow().strftime("%Y-%m-%d")}
        PATIENT SYMPTOMS: {symptom}
        ASSESSMENT: {result.get("possible_conditions", "Unknown")}
        CONFIDENCE: {result.get("confidence", "Unknown")}%
        CARE RECOMMENDATION: {result.get("care_recommendation", "Consult a healthcare provider")}
        NOTES: For a definitive diagnosis, consult a healthcare provider.
        """
        report_data = {
            "user_id": user_id or generate_temp_user_id(request),
            "timestamp": datetime.utcnow().isoformat(),
            "symptom": symptom,
            "condition_common": result.get("possible_conditions", "Unknown").split("(")[0].strip() if "(" in result.get("possible_conditions", "") else result.get("possible_conditions", "Unknown"),
            "condition_medical": result.get("possible_conditions", "").split("(")[1].split(")")[0].strip() if "(" in result.get("possible_conditions", "") and ")" in result.get("possible_conditions", "") else "N/A",
            "confidence": result.get("confidence", 0),
            "triage_level": result.get("triage_level", "MODERATE"),
            "care_recommendation": result.get("care_recommendation", "Consult a healthcare provider")
        }
        report_url = generate_pdf_report(report_data)

        if user_id:
            symptom_log = SymptomLog(
                user_id=user_id,
                symptom=symptom,
                response=json.dumps(result),
                condition_common=report_data["condition_common"],
                condition_medical=report_data["condition_medical"],
                confidence=report_data["confidence"],
                triage_level=report_data["triage_level"],
                care_recommendation=report_data["care_recommendation"],
                created_at=datetime.utcnow()
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
        logger.error(f"Error generating report: {str(e)}")
        return jsonify({"error": "Failed to generate report", "success": False}), 500