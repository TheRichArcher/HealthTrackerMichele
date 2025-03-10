from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from backend.models import User, SymptomLog, Report, UserTierEnum, CareRecommendationEnum
from backend.extensions import db
from backend.openai_config import clean_ai_response, SYSTEM_PROMPT
import openai
import os
import json
import logging
from datetime import datetime
import time
import re

symptom_routes = Blueprint("symptom_routes", __name__, url_prefix="/api/symptoms")

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_FREE_MESSAGES = 15  # Kept for reference, but not enforced
MIN_CONFIDENCE_THRESHOLD = 95  # Keeping at 95% as requested
MAX_TOKENS = 1500
TEMPERATURE = 0.7

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
    # Create a custom system prompt that addresses the issues
    custom_system_prompt = """You are Michele, an AI medical assistant designed to mimic a doctor's visit. Your goal is to understand the user's symptoms through conversation and provide insights only when highly confident.

CRITICAL INSTRUCTIONS:
1. ALWAYS return a valid JSON response with these exact fields:
   - "is_assessment": boolean (true only if confidence ≥ 95% for a diagnosis)
   - "is_question": boolean (true if asking a follow-up question)
   - "possible_conditions": string or array (question text if is_question, FULL CONDITION NAME if is_assessment)
   - "confidence": number (0-100, null if no assessment)
   - "triage_level": string ("MILD", "MODERATE", "SEVERE", null if no assessment)
   - "care_recommendation": string (brief advice, null if no assessment)
   - "requires_upgrade": boolean (set by backend, default false)
   Optional:
   - "assessment": object (if is_assessment=true, with "conditions", "triage_level", "care_recommendation")
   - "doctors_report": string (if requested)

2. For assessments (is_assessment=true):
   - Include an "assessment" object: {"conditions": [{"name": "Medical Term (Common Name)", "confidence": number}], "triage_level": string, "care_recommendation": string}
   - Only provide an assessment if confidence is ≥ 95%.
   - ALWAYS format condition names as "Medical Term (Common Name)" - e.g., "Allergic Rhinitis (Hay Fever)" or "Conjunctivitis (Pink Eye)"
   - NEVER mask condition names with asterisks or other characters.

3. Conversation flow:
   - For the first user message, set "is_question": true and ask ONE clear follow-up question.
   - Ask ONE clear, single question at a time until you reach ≥ 95% confidence or gather enough context. Do NOT ask multiple questions in one response—wait for the user's answer before asking another.
   - Avoid diagnosing unless confidence meets the threshold.
   - For potentially serious conditions (e.g., stroke, heart attack), ask differentiating questions until certain.
   - For common conditions (e.g., common cold, sunburn), suggest home care if appropriate.

4. CRITICAL SAFETY INSTRUCTION: Always follow a 'rule-out worst first' approach. For any symptom presentation, first consider and rule out life-threatening conditions before suggesting benign diagnoses.

5. IMPORTANT: For chest discomfort, shortness of breath, or related symptoms, ALWAYS consider cardiovascular causes first (heart attack, angina, etc.) before respiratory conditions.

6. Be concise, empathetic, and precise. Avoid guessing—ask questions if unsure.
7. Include "doctors_report" as a formatted string only when explicitly requested."""
    
    messages = [{
        "role": "system",
        "content": custom_system_prompt
    }]
    for entry in conversation_history:
        role = "assistant" if entry.get("isBot", False) else "user"
        content = entry.get("message", "")
        messages.append({"role": role, "content": content})
    if not conversation_history or conversation_history[-1].get("isBot", False):
        messages.append({"role": "user", "content": symptom})
    return messages

def ensure_proper_condition_format(condition_name):
    """Ensure condition name follows the 'Medical Term (Common Name)' format."""
    if not condition_name:
        return "Unknown Condition"
    
    # Remove any asterisks
    cleaned = condition_name.replace("*", "")
    
    # Check if it already has the format "Something (Something Else)"
    if re.search(r'.*\(.*\).*', cleaned):
        return cleaned
    
    # If no parentheses, add a generic common name
    return f"{cleaned} (Medical Condition)"

def call_openai_api(messages, retry_count=0):
    """Call the OpenAI API with retry logic for rate limits or errors."""
    if retry_count >= MAX_RETRIES:
        logger.error("Max retries reached for OpenAI API call")
        raise RuntimeError("Failed to get response from OpenAI")
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",  # Changed from gpt-4-turbo to gpt-4o
            messages=messages,
            response_format={"type": "json_object"},  # Force JSON response
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        content = response.choices[0].message.content.strip() if response.choices else ""
        logger.info(f"Raw OpenAI response: {content[:100]}...")  # Log first 100 chars
        
        # Validate JSON format
        try:
            parsed_json = json.loads(content)
            
            # Fix any asterisks in condition names and ensure proper format
            if "possible_conditions" in parsed_json:
                if isinstance(parsed_json["possible_conditions"], str):
                    parsed_json["possible_conditions"] = ensure_proper_condition_format(parsed_json["possible_conditions"])
                elif isinstance(parsed_json["possible_conditions"], list):
                    parsed_json["possible_conditions"] = [ensure_proper_condition_format(c) for c in parsed_json["possible_conditions"]]
            
            # Fix assessment object if present
            if "assessment" in parsed_json and isinstance(parsed_json["assessment"], dict):
                if "conditions" in parsed_json["assessment"] and isinstance(parsed_json["assessment"]["conditions"], list):
                    for condition in parsed_json["assessment"]["conditions"]:
                        if "name" in condition:
                            condition["name"] = ensure_proper_condition_format(condition["name"])
            
            content = json.dumps(parsed_json)
            
        except json.JSONDecodeError:
            logger.warning(f"GPT-4o returned invalid JSON: {content[:100]}...")
            if retry_count < MAX_RETRIES:
                # Add explicit instruction to return JSON and retry
                messages.append({
                    "role": "user", 
                    "content": "Please respond in valid JSON format only, following the structure I specified. Format condition names as 'Medical Term (Common Name)' and do not mask with asterisks."
                })
                time.sleep(RETRY_DELAY)
                return call_openai_api(messages, retry_count + 1)
        
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

def post_process_assessment(result):
    """Post-process assessment to ensure proper display."""
    if not result.get("is_assessment", False):
        return result
    
    # Get the condition name
    condition_name = ""
    if isinstance(result.get("possible_conditions"), list) and result["possible_conditions"]:
        condition_name = result["possible_conditions"][0]
    elif isinstance(result.get("possible_conditions"), str):
        condition_name = result["possible_conditions"]
    
    # Ensure proper format
    condition_name = ensure_proper_condition_format(condition_name)
    
    # Update the result with the formatted condition name
    if isinstance(result.get("possible_conditions"), list):
        result["possible_conditions"][0] = condition_name
    else:
        result["possible_conditions"] = condition_name
    
    # Add assessment field if not present
    if "assessment" not in result:
        result["assessment"] = {
            "conditions": [{"name": condition_name, "confidence": result.get("confidence", 95)}],
            "triage_level": result.get("triage_level", "MODERATE"),
            "care_recommendation": result.get("care_recommendation", "")
        }
    elif "conditions" in result["assessment"]:
        # Ensure condition names in assessment are properly formatted
        for condition in result["assessment"]["conditions"]:
            if "name" in condition:
                condition["name"] = ensure_proper_condition_format(condition["name"])
    
    return result

def override_confidence_threshold(result):
    """Override the confidence threshold check to use 95% instead of 90%."""
    if result.get("is_assessment", False) and result.get("confidence", 0) < MIN_CONFIDENCE_THRESHOLD:
        result["is_assessment"] = False
        result["is_question"] = True
        result["possible_conditions"] = "I need more details to be certain—can you describe any other symptoms?"
        result["confidence"] = None
        result["triage_level"] = None
        result["care_recommendation"] = None
        if "assessment" in result:
            del result["assessment"]
    return result

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
    """Analyze user symptoms and iterate questions until confidence threshold is met."""
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
        return reset_conversation()

    messages = prepare_conversation_messages(symptom, conversation_history)
    try:
        response_text = call_openai_api(messages)
        result = clean_ai_response(response_text, current_user, conversation_history, symptom)
        
        # Apply our 95% confidence threshold override
        result = override_confidence_threshold(result)
        
        # Post-process assessment to ensure proper display
        if result.get("is_assessment", False):
            result = post_process_assessment(result)
        
        logger.info(f"Processed AI result: {json.dumps(result)[:200]}...")

        if not is_premium_user(current_user):
            user_messages = sum(1 for msg in conversation_history if not msg.get("isBot", False))
            triage_level = (result.get("triage_level") or "").upper()
            if result.get("is_assessment", False) and triage_level in ["MODERATE", "SEVERE"]:
                result["requires_upgrade"] = True

        # Continue asking questions if confidence is below threshold or is_question is true
        if result.get("is_question", False):
            next_question = result.get("possible_conditions", "Can you tell me more about your symptoms?")
            conversation_history.append({"message": next_question, "isBot": True})
            return jsonify({
                "response": next_question,
                "isBot": True,
                "conversation_history": conversation_history
            }), 200
        else:
            # Provide assessment
            if user_id and result.get("is_assessment", False):
                save_symptom_interaction(
                    user_id,
                    symptom,
                    result,
                    result.get("care_recommendation", ""),
                    result.get("confidence", 0),
                    True
                )
            return jsonify({
                "response": result,
                "isBot": True,
                "conversation_history": conversation_history
            }), 200

    except json.JSONDecodeError:
        logger.error(f"Failed to parse OpenAI response as JSON: {response_text[:200]}...")
        return jsonify({
            "response": "I'm having trouble processing that. Can you tell me more about your symptoms?",
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
        result = clean_ai_response(response_text, current_user, conversation_history, symptom)
        
        # Apply our 95% confidence threshold override
        result = override_confidence_threshold(result)
        
        # Post-process assessment to ensure proper display
        if result.get("is_assessment", False):
            result = post_process_assessment(result)

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

    return jsonify({
        "message": "Conversation reset successfully",
        "response": "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health.\n\nYou can start by describing your symptoms like:\n• \"I've had a headache for two days\"\n• \"My throat is sore and I have a fever\"\n• \"I have a rash on my arm that's itchy\"",
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
        result = clean_ai_response(response_text, current_user, test_history, test_symptom)
        
        # Apply our 95% confidence threshold override
        result = override_confidence_threshold(result)
        
        # Post-process assessment to ensure proper display
        if result.get("is_assessment", False):
            result = post_process_assessment(result)
            
        logger.info(f"Debug result for user {user_id or 'Anonymous'}: {json.dumps(result)[:200]}...")
        return jsonify({
            "symptom": test_symptom,
            "processed_result": result,
            "requires_upgrade": result.get("requires_upgrade", False),
            "user_tier": current_user.subscription_tier
        }), 200
    except Exception as e:
        logger.error(f"Debug error for user {user_id or 'Anonymous'}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500