from flask import Blueprint, request, jsonify
from backend.routes.extensions import db
from backend.models import Symptom, SymptomLog
from datetime import datetime
from dotenv import load_dotenv
import openai
import logging
import time
import re
import os
from typing import Optional

# Load environment variables from .env in backend folder
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

# Get OpenAI API key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    logging.warning("⚠️ OpenAI API key is missing! Make sure .env is loaded.")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Blueprint setup - removed url_prefix to let app.py handle it
onboarding_routes = Blueprint('onboarding_routes', __name__)

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
CONFIDENCE_THRESHOLD = 90
CONFIDENCE_INCREMENT = 15
MAX_QUESTIONS_PER_SESSION = 20
SEVERITY_SCORE_THRESHOLD = 9
MODEL_NAME = "gpt-4"
MAX_TOKENS = 400
DEFAULT_TEMPERATURE = 0.7

EMERGENCY_KEYWORDS = [
    "chest pain", "shortness of breath", "tightness", "weakness", 
    "slurred speech", "fainting", "vision loss", "abnormal heartbeat",
    "numbness", "severe headache"
]

def normalize_time_phrases(response: str) -> str:
    """Normalize time-related phrases in the response."""
    vague_time_phrases = {
        r"this morning": "8 hours ago",
        r"for a while": "a few hours",
        r"since yesterday": "24 hours ago",
        r"immediately": "just now",
        r"a long time": "several hours",
        r"off and on": "intermittently"
    }
    for phrase, normalized in vague_time_phrases.items():
        response = re.sub(phrase, normalized, response, flags=re.IGNORECASE)
    return response

def check_for_emergency(symptom_text: str, severity_score: int) -> bool:
    """Check if symptoms indicate an emergency situation."""
    count = sum(1 for keyword in EMERGENCY_KEYWORDS if re.search(rf"\b{re.escape(keyword)}\b", symptom_text, re.IGNORECASE))
    return count >= 2 or severity_score >= SEVERITY_SCORE_THRESHOLD

def send_openai_request(prompt: str) -> str:
    """Send request to OpenAI API with proper error handling and retries."""
    fallback_question = "Can you provide more details?"
    
    if not api_key:
        logger.error("OpenAI API key is missing")
        return fallback_question

    client = openai.OpenAI(api_key=api_key)

    for attempt in range(MAX_RETRIES):
        try:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Sending OpenAI request (attempt {attempt + 1})")
                logger.debug(f"Prompt: {prompt}")

            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a medical assistant helping with symptom analysis."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=MAX_TOKENS,
                temperature=DEFAULT_TEMPERATURE
            )

            response_text = response.choices[0].message.content.strip() if response.choices else ""
            if not response_text:
                logger.error(f"Empty response from OpenAI (attempt {attempt + 1})")
                if attempt == MAX_RETRIES - 1:
                    return fallback_question
                time.sleep(RETRY_DELAY)
                continue

            return response_text

        except openai.RateLimitError as e:
            logger.error(f"OpenAI rate limit exceeded (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return fallback_question
            time.sleep(RETRY_DELAY * (attempt + 2))  # Longer delay for rate limits

        except openai.APIConnectionError as e:
            logger.error(f"OpenAI API connection error (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return fallback_question
            time.sleep(RETRY_DELAY * (attempt + 1))

        except openai.APIError as e:
            logger.error(f"OpenAI API error (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return fallback_question
            time.sleep(RETRY_DELAY * (attempt + 1))

        except openai.AuthenticationError as e:
            logger.error(f"OpenAI authentication error: {e}")
            return fallback_question

        except openai.InvalidRequestError as e:
            logger.error(f"OpenAI invalid request error: {e}")
            return fallback_question

        except Exception as e:
            logger.error(f"Unexpected error (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return fallback_question
            time.sleep(RETRY_DELAY)

    return fallback_question

def ensure_single_question(response_text: str) -> str:
    """Extract and return a single question from the response."""
    questions = [q.strip() for q in response_text.split('?') if q.strip()]
    return questions[0] + "?" if questions else "Can you provide more information?"

@onboarding_routes.route("/", methods=["POST"])
def onboarding():
    """Handle the onboarding process and symptom logging."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        initial_symptom = data.get("initial_symptom", "").strip().lower()
        previous_answers = normalize_time_phrases(data.get("previous_answers", "").strip())
        question_count = int(data.get("question_count", 0))
        confidence_score = int(data.get("confidence_score", 0))

        if question_count >= MAX_QUESTIONS_PER_SESSION:
            return jsonify({"next_question": "Onboarding complete! Thank you."})

        if check_for_emergency(initial_symptom + " " + previous_answers, confidence_score):
            return jsonify({"next_question": "Your symptoms may indicate a serious issue. Seek immediate medical attention."})

        if confidence_score >= CONFIDENCE_THRESHOLD:
            return jsonify({"next_question": "Onboarding complete! We've gathered enough information."})

        try:
            # Check if symptom exists, create if it doesn't
            symptom_obj = Symptom.query.filter_by(name=initial_symptom).first()
            if not symptom_obj:
                symptom_obj = Symptom(name=initial_symptom)
                db.session.add(symptom_obj)
                db.session.commit()

            new_log = SymptomLog(
                user_id=user_id,
                symptom_id=symptom_obj.id,
                notes=previous_answers,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

        except Exception as db_error:
            logger.error(f"Database error: {str(db_error)}")
            db.session.rollback()
            return jsonify({"error": "Error saving symptom information"}), 500

        system_instruction = (
            "You are a knowledgeable medical assistant guiding a patient through diagnostic questions. "
            "Ask one specific follow-up question at a time. Avoid repeated questions on the same topic unless necessary."
        )
        prompt = (
            f"The patient mentioned: '{initial_symptom}'.\n"
            f"Details so far: '{previous_answers}'.\n"
            f"{system_instruction} What is a relevant follow-up question?"
        )

        next_question = send_openai_request(prompt)
        next_question = ensure_single_question(next_question)

        return jsonify({
            "next_question": next_question,
            "question_count": question_count + 1,
            "confidence_score": confidence_score,
            "logged_symptom": {
                "id": new_log.id,
                "symptom": symptom_obj.name,
                "notes": new_log.notes,
                "timestamp": new_log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            }
        })

    except Exception as e:
        logger.error(f"Error during onboarding: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Unexpected error during onboarding."}), 500