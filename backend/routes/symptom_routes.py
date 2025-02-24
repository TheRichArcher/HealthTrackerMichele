from flask import Blueprint, request, jsonify
from backend.routes.extensions import db
from backend.models import SymptomLog
from datetime import datetime
from dotenv import load_dotenv
import openai
import logging
import time
import re
import os
from typing import Any
from backend.routes.openai_config import (
    SYSTEM_PROMPT,
    clean_ai_response,
    MIN_CONFIDENCE,
    MAX_CONFIDENCE,
    DEFAULT_CONFIDENCE,
    ResponseSection,
    calculate_confidence
)

# Load environment variables from .env in backend folder
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

# Set OpenAI API key
openai.api_key = os.environ.get("OPENAI_API_KEY")

if not openai.api_key:
    logging.warning("⚠️ OpenAI API key is missing! Make sure .env is loaded.")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Blueprint setup
symptom_routes = Blueprint("symptom_routes", __name__)

# Constants
MAX_INPUT_LENGTH = 1000
DEFAULT_TEMPERATURE = 0.7
MAX_TOKENS = 750
MODEL_NAME = "gpt-4"
MAX_RETRIES = 3
RETRY_DELAY = 2

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

def create_error_response(message: str, status_code: int) -> tuple[Any, int]:
    """Create standardized error response."""
    return jsonify({
        'possible_conditions': message,
        'triage_level': TriageLevel.MODERATE,
        'confidence': MIN_CONFIDENCE
    }), status_code

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

@symptom_routes.route("/analyze", methods=["POST"])
def analyze_symptoms() -> tuple[Any, int]:
    """Handle AI analysis of symptoms."""
    try:
        data = request.get_json()
        symptoms = sanitize_input(data.get('symptoms', ''))
        conversation_history = data.get('conversation_history', [])

        if not symptoms:
            return create_error_response("Please describe your symptoms.", 400)

        if not openai.api_key:
            logger.error("OpenAI API key is missing")
            return create_error_response("AI service is temporarily unavailable.", 503)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": symptoms})

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Sending request to OpenAI with messages: %s", messages)

        for attempt in range(MAX_RETRIES):
            try:
                response = openai.ChatCompletion.create(
                    model=MODEL_NAME,
                    messages=messages,
                    temperature=DEFAULT_TEMPERATURE,
                    max_tokens=MAX_TOKENS
                )

                response_text = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if not response_text:
                    logger.error(f"Empty response from OpenAI (attempt {attempt + 1})")
                    if attempt == MAX_RETRIES - 1:
                        return create_error_response("Invalid response from AI service.", 500)
                    time.sleep(RETRY_DELAY)
                    continue

                ai_response = clean_ai_response(response_text)
                confidence_score = calculate_confidence(ai_response)
                triage_level = determine_triage_level(ai_response, symptoms)
                
                response_data = {
                    'possible_conditions': ai_response,
                    'triage_level': triage_level,
                    'confidence': confidence_score
                }

                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Final response data: %s", response_data)

                return jsonify(response_data)

            except Exception as e:
                logger.error(f"OpenAI API Error (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return create_error_response("Error communicating with AI service.", 500)
                time.sleep(RETRY_DELAY * (attempt + 1))

        return create_error_response("Maximum retries reached with AI service.", 500)

    except Exception as e:
        logger.error("Error analyzing symptoms: %s", str(e))
        return create_error_response("Unable to process your request.", 500)