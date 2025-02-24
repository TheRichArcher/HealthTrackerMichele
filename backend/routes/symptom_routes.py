from flask import Blueprint, request, jsonify
from backend.routes.extensions import db
from backend.models import SymptomLog
from datetime import datetime
from typing import Any
import logging
import openai
import os
import re
from backend.routes.openai_config import (
    SYSTEM_PROMPT,
    clean_ai_response,
    MIN_CONFIDENCE,
    MAX_CONFIDENCE,
    DEFAULT_CONFIDENCE,
    ResponseSection,
    calculate_confidence
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger("symptom_routes")

# Blueprint setup
symptom_routes = Blueprint("symptom_routes", __name__)

# Constants
MAX_INPUT_LENGTH = 1000
DEFAULT_TEMPERATURE = 0.7
MAX_TOKENS = 750
MODEL_NAME = "gpt-4-turbo-preview"

class TriageLevel:
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"

def sanitize_input(text: str) -> str:
    """Sanitize user input by removing excess whitespace and special characters."""
    if not isinstance(text, str):
        return ""
    text = " ".join(text.split())
    text = re.sub(r'[^a-zA-Z0-9\s.,!?-]', '', text)
    return text[:MAX_INPUT_LENGTH]

@symptom_routes.route("/", methods=["POST", "GET"])
def symptoms() -> tuple[Any, int]:
    """Handle symptom logging and retrieval."""
    if request.method == "POST":
        try:
            data = request.get_json()
            user_id = data.get("user_id")
            symptom_name = sanitize_input(data.get("symptom", "")).lower()
            notes = sanitize_input(data.get("notes", ""))

            if not user_id or not symptom_name:
                return jsonify({"error": "User ID and symptom name are required."}), 400

            new_log = SymptomLog(
                user_id=user_id,
                symptom=symptom_name,
                notes=notes,
                date=datetime.utcnow(),
            )
            db.session.add(new_log)
            db.session.commit()

            logger.info("Symptom logged: %s (User %s)", symptom_name, user_id)
            return jsonify({
                "message": "Symptom logged successfully.",
                "logged_symptom": {
                    "id": new_log.id,
                    "symptom": new_log.symptom,
                    "notes": new_log.notes,
                    "date": new_log.date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            }), 201

        except Exception as e:
            db.session.rollback()
            logger.error("Error logging symptom: %s", str(e))
            return jsonify({"error": "Failed to log symptom."}), 500

    # GET method
    try:
        symptoms = SymptomLog.query.all()
        return jsonify({
            "symptoms": [{
                "id": log.id,
                "user_id": log.user_id,
                "symptom": log.symptom,
                "notes": log.notes,
                "date": log.date.strftime("%Y-%m-%d %H:%M:%S")
            } for log in symptoms]
        }), 200
    except Exception as e:
        logger.error("Error retrieving symptoms: %s", str(e))
        return jsonify({"error": "Failed to retrieve symptoms"}), 500

def determine_triage_level(ai_response: str, symptoms: str) -> str:
    """Determine triage level based on symptoms and AI response."""
    response_lower = ai_response.lower()
    symptoms_lower = symptoms.lower()

    emergency_terms = [
        "chest pain", "difficulty breathing", "shortness of breath",
        "severe allergic reaction", "anaphylaxis", "unconscious",
        "stroke", "heart attack", "severe bleeding", "head injury",
        "severe confusion", "severe headache", "sudden vision loss",
        "coughing up blood", "severe abdominal pain", "suicide",
        "overdose", "seizure", "severe burn"
    ]
    
    if any(term in response_lower or term in symptoms_lower for term in emergency_terms):
        logger.warning("Emergency condition detected in symptoms")
        return TriageLevel.SEVERE

    urgent_terms = [
        "moderate to severe", "worsening", "persistent",
        "getting worse", "concerning", "unusual pain"
    ]

    if any(term in response_lower for term in urgent_terms):
        return TriageLevel.MODERATE

    mild_conditions = [
        ('allergy', ['cat', 'dust', 'pollen', 'sneez']),
        ('cold', ['runny nose', 'sore throat', 'cough']),
        ('minor', ['headache', 'muscle ache']),
        ('common', ['tired', 'fatigue']),
        ('mild', ['discomfort', 'irritation'])
    ]

    for condition, symptoms_list in mild_conditions:
        if (condition in symptoms_lower or any(s in symptoms_lower for s in symptoms_list)) and \
           not any(emergency in response_lower for emergency in emergency_terms):
            return TriageLevel.MILD

    return TriageLevel.MODERATE

def create_error_response(message: str, status_code: int) -> tuple[Any, int]:
    """Create standardized error response."""
    return jsonify({
        'possible_conditions': message,
        'triage_level': TriageLevel.MODERATE,
        'confidence': MIN_CONFIDENCE
    }), status_code

@symptom_routes.route("/analyze", methods=["POST"])
def analyze_symptoms() -> tuple[Any, int]:
    """Handle AI analysis of symptoms."""
    try:
        data = request.get_json()
        symptoms = sanitize_input(data.get('symptoms', ''))
        conversation_history = data.get('conversation_history', [])

        if not symptoms:
            return create_error_response("Please describe your symptoms.", 400)

        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            logger.error("OpenAI API key is missing")
            return create_error_response("AI service is temporarily unavailable.", 503)

        client = openai.OpenAI(api_key=openai_api_key)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": symptoms})

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Sending request to OpenAI with messages: %s", messages)

        try:
            # Updated OpenAI API call for version 1.0+
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=MAX_TOKENS
            )

            if not response or not response.choices:
                logger.error("Invalid response from OpenAI: %s", response)
                return create_error_response("Invalid response from AI service.", 500)

            raw_response = response.choices[0].message.content

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Raw OpenAI response: %s", raw_response)

        except Exception as e:
            logger.error("OpenAI API error: %s", str(e))
            return create_error_response("Error communicating with AI service.", 500)

        # Clean and structure the response
        ai_response = clean_ai_response(raw_response)

        # Parse sections more reliably
        conditions_match = re.search(r'Possible Conditions:\s*(.+?)(?=\nConfidence Level:|$)', ai_response, re.DOTALL)
        confidence_match = re.search(r'Confidence Level:\s*(\d+)', ai_response)
        care_match = re.search(r'Care Recommendation:\s*(mild|moderate|severe)', ai_response, re.IGNORECASE)

        # Extract and validate conditions
        conditions = conditions_match.group(1).strip() if conditions_match else "Unable to determine conditions"
        
        # Calculate confidence using both explicit value and content analysis
        explicit_confidence = int(confidence_match.group(1)) if confidence_match else None
        calculated_confidence = calculate_confidence(conditions)
        
        # Use the higher confidence value, but respect MIN/MAX bounds
        final_confidence = max(
            calculated_confidence,
            explicit_confidence if explicit_confidence is not None else MIN_CONFIDENCE
        )
        final_confidence = min(max(final_confidence, MIN_CONFIDENCE), MAX_CONFIDENCE)

        # Determine care recommendation
        initial_care = care_match.group(1).lower() if care_match else TriageLevel.MODERATE
        suggested_triage = determine_triage_level(conditions, symptoms)
        
        # Always use SEVERE if detected, otherwise use AI's recommendation
        final_triage = suggested_triage if suggested_triage == TriageLevel.SEVERE else initial_care

        # Construct the response
        response_data = {
            'possible_conditions': conditions,
            'triage_level': final_triage,
            'confidence': final_confidence
        }

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Final response data: %s", response_data)

        return jsonify(response_data)

    except Exception as e:
        logger.error("Error analyzing symptoms: %s", str(e))
        return create_error_response("Unable to process your request.", 500)