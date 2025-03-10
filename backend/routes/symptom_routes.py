from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from backend.models import User, SymptomLog, Report, UserTierEnum, CareRecommendationEnum
from backend.extensions import db
from backend.openai_config import SYSTEM_PROMPT
import openai
import os
import json
import logging
from datetime import datetime
import time

symptom_routes = Blueprint("symptom_routes", __name__, url_prefix="/api/symptoms")

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_FREE_MESSAGES = 15
MIN_CONFIDENCE_THRESHOLD = 99  # Updated to 99% for high accuracy
MAX_TOKENS = 1500
TEMPERATURE = 0.7
MAX_QUESTIONS = 20  # Limit to prevent excessive questioning

openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set")

logger = logging.getLogger(__name__)

class MockUser:
    subscription_tier = UserTierEnum.FREE.value

def is_premium_user(user):
    """Check if the user has a premium subscription."""
    return getattr(user, "subscription_tier", UserTierEnum.FREE.value) in {
        UserTierEnum.PAID.value,
        UserTierEnum.ONE_TIME.value
    }

def prepare_conversation_messages(symptom, conversation_history):
    """Prepare the message array for OpenAI based on history and current symptom."""
    messages = [{
        "role": "system",
        "content": (
            "You are a medical assistant aiming for 99% diagnostic accuracy. Analyze the user's symptoms based on the conversation history. "
            "Provide a possible condition with a confidence level (0-100), triage level (LOW, MODERATE, SEVERE), and care recommendation. "
            "Consider all differentials (e.g., vertigo, heat exhaustion, heat stroke, dehydration) and environmental factors (e.g., heat, hydration). "
            "If confidence is below 99%, suggest one specific follow-up question to reach higher certainty. Ask only one question at a time. "
            "Always return your response in strict JSON format, even for questions:\n"
            "{\n"
            "  \"possible_conditions\": [\"condition_name\"],\n"
            "  \"confidence\": number,\n"
            "  \"triage_level\": \"LEVEL\",\n"
            "  \"care_recommendation\": \"recommendation\",\n"
            "  \"next_question\": \"question or null\"\n"
            "}"
        )
    }]
    for entry in conversation_history:
        role = "assistant" if entry.get("isBot", False) else "user"
        content = entry.get("message", "")
        messages.append({"role": role, "content": content})
    if not conversation_history or conversation_history[-1].get("isBot", False):
        messages.append({"role": "user", "content": symptom})
    return messages

def call_openai_api(messages, retry_count=0):
    """Call the OpenAI API with retry logic for rate limits or errors."""
    if retry_count >= MAX_RETRIES:
        logger.error("Max retries reached for OpenAI API call")
        raise RuntimeError("Failed to get response from OpenAI")
    try:
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        content = response.choices[0].message.content.strip() if response.choices else ""
        logger.info(f"Raw OpenAI response: {content}")
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
        raise
    except Exception as e:
        logger.error(f"Unexpected error calling OpenAI API: {str(e)}", exc_info=True)
        raise

def save_symptom_interaction(user_id, symptom_text, ai_response, care_recommendation, confidence, is_assessment):
    """Save symptom interaction and generate a report if it's an assessment."""
    try:
        response_text = json.dumps(ai_response) if isinstance(ai_response, dict) else ai_response
        new_symptom = SymptomLog(
            user_id=user_id,
            symptom_name=symptom_text,
            notes=response_text,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_symptom)
        db.session.commit()

        if is_assessment:
            care_recommendation_enum = CareRecommendationEnum.SEE_DOCTOR
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
                title=f"Assessment Report - {datetime.utcnow().strftime('%Y-%m-%d')}",
                content=json.dumps(report_content),
                care_recommendation=care_recommendation_enum,
                created_at=datetime.utcnow()
            )
            db.session.add(new_report)
            db.session.commit()
            logger.info(f"Created report with ID: {new_report.id} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving symptom interaction for user {user_id}: {str(e)}", exc_info=True)
        db.session.rollback()
        return False

@symptom_routes.route("/analyze", methods=["POST"])
def analyze_symptoms():
    """Analyze user symptoms and iterate questions until 99% confidence or max questions."""
    logger.info("Processing symptom analysis request")
    is_production = current_app.config.get("ENV") == "production"

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
            logger.warning(f"Invalid token: {str(e)}")

    data = request.get_json() or {}
    symptom = data.get("symptom", "").strip()
    conversation_history = data.get("conversation_history", [])
    context_notes = data.get("context_notes", "")
    reset = data.get("reset", False)

    if not symptom or not isinstance(symptom, str):
        logger.warning("Invalid or missing symptom input")
        return jsonify({
            "response": "Please describe your symptoms.",
            "isBot": True,
            "conversation_history": conversation_history
        }), 400

    if not isinstance(conversation_history, list):
        logger.warning("Invalid conversation_history format")
        return jsonify({"error": "Conversation history must be a list."}), 400

    for entry in conversation_history:
        if not isinstance(entry, dict) or "message" not in entry or "isBot" not in entry:
            logger.warning(f"Invalid conversation history entry: {entry}")
            return jsonify({"error": "Each conversation history entry must have 'message' and 'isBot' fields."}), 400
        if not isinstance(entry["message"], str) or not isinstance(entry["isBot"], bool):
            logger.warning(f"Invalid types in conversation history entry: {entry}")
            return jsonify({"error": "'message' must be string, 'isBot' must be boolean."}), 400

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
            "response": "Hello! I'm your AI medical assistant. Please describe your symptoms.",
            "isBot": True,
            "conversation_history": []
        }), 200

    # Count questions asked so far
    question_count = sum(1 for msg in conversation_history if msg.get("isBot") and "Next Question" in msg.get("message", ""))
    if question_count >= MAX_QUESTIONS:
        # Force an assessment if max questions reached
        messages = prepare_conversation_messages(symptom, conversation_history)
        response_text = call_openai_api(messages)
        result = json.loads(response_text)
        logger.info(f"Forced assessment result: {result}")

        if user_id:
            save_symptom_interaction(
                user_id,
                symptom,
                result,
                result.get("care_recommendation", ""),
                result.get("confidence", 0),
                True  # Force assessment
            )

        return jsonify({
            "response": result,
            "isBot": True,
            "conversation_history": conversation_history
        }), 200

    messages = prepare_conversation_messages(symptom, conversation_history)
    try:
        response_text = call_openai_api(messages)
        result = json.loads(response_text)
        logger.info(f"Processed AI result: {result}")

        if not is_premium_user(current_user):
            user_messages = sum(1 for msg in conversation_history if not msg.get("isBot", False))
            triage_level = (result.get("triage_level") or "").upper()
            if user_messages >= MAX_FREE_MESSAGES or (result.get("is_assessment", False) and triage_level in ["MODERATE", "SEVERE"]):
                result["requires_upgrade"] = True

        if result.get("confidence", 0) < MIN_CONFIDENCE_THRESHOLD and result.get("next_question"):
            conversation_history.append({"message": f"Next Question: {result['next_question']}", "isBot": True})
            return jsonify({
                "response": result["next_question"],
                "isBot": True,
                "conversation_history": conversation_history
            }), 200

        if user_id and result.get("is_assessment", False):
            save_symptom_interaction(
                user_id,
                symptom,
                result,
                result.get("care_recommendation", ""),
                result.get("confidence", 0),
                True  # Assessment
            )

        return jsonify({
            "response": result,
            "isBot": True,
            "conversation_history": conversation_history
        }), 200
    except json.JSONDecodeError:
        logger.error(f"Failed to parse OpenAI response as JSON: {response_text}")
        return jsonify({
            "response": "I’m having trouble processing that. Can you tell me more about your symptoms?",
            "isBot": True,
            "conversation_history": conversation_history
        }), 200
    except Exception as e:
        logger.error(f"Error in symptom analysis: {str(e)}", exc_info=True)
        return jsonify({
            "response": "Error processing your request. Please try again.",
            "isBot": True,
            "conversation_history": conversation_history
        }), 500

@symptom_routes.route("/history", methods=["GET"])
def get_symptom_history():
    """Retrieve the user's symptom history."""
    logger.info("Processing symptom history request")
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

        symptoms = SymptomLog.query.filter_by(user_id=user_id).order_by(SymptomLog.timestamp.desc()).all()
        result = []
        for symptom in symptoms:
            try:
                response_data = json.loads(symptom.notes) if isinstance(symptom.notes, str) else symptom.notes
                report = Report.query.filter_by(user_id=user_id, created_at=symptom.timestamp).first()
                entry = {
                    "id": symptom.id,
                    "description": symptom.symptom_name,
                    "created_at": symptom.timestamp.isoformat(),
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
                    "description": symptom.symptom_name,
                    "created_at": symptom.timestamp.isoformat(),
                    "error": "Failed to process response"
                })
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error retrieving symptom history for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@symptom_routes.route("/doctor-report", methods=["POST"])
def generate_doctor_report():
    """Generate a doctor report for premium or one-time purchase users."""
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
        return jsonify({"error": "Symptom is required."}), 400

    messages = prepare_conversation_messages(symptom, conversation_history)
    messages[-1]["content"] += " Generate a comprehensive medical report suitable for healthcare providers."

    try:
        response_text = call_openai_api(messages)
        result = json.loads(response_text)

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
            symptom_record = SymptomLog.query.filter_by(user_id=user_id, symptom_name=symptom).order_by(SymptomLog.timestamp.desc()).first()
            if not symptom_record:
                symptom_record = SymptomLog(
                    user_id=user_id,
                    symptom_name=symptom,
                    notes="One-time doctor's report generated",
                    timestamp=datetime.utcnow()
                )
                db.session.add(symptom_record)
                db.session.commit()

            report_content = {
                "doctors_report": doctor_report,
                "care_recommendation": result.get("care_recommendation", ""),
                "generated_at": datetime.utcnow().isoformat(),
                "one_time_purchase": True
            }

            existing_report = Report.query.filter_by(user_id=user_id, created_at=symptom_record.timestamp).first()
            if existing_report:
                existing_report.content = json.dumps(report_content)
                existing_report.created_at = datetime.utcnow()
            else:
                new_report = Report(
                    user_id=user_id,
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
    """Reset the conversation history."""
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
        "response": "Hello! I'm your AI medical assistant. Please describe your symptoms.",
        "isBot": True,
        "conversation_history": []
    }), 200

@symptom_routes.route("/debug", methods=["GET"])
def debug_route():
    """Debug endpoint for testing symptom analysis."""
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
        result = json.loads(response_text)
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