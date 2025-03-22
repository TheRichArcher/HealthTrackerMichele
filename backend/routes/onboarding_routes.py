from flask import Blueprint, request, jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from backend.extensions import db
from backend.models import SymptomLog, User, UserTierEnum
from datetime import datetime
import logging
import re
import os
from backend.utils.openai_utils import call_openai_api

# Load environment variables from .env in backend folder
os.environ.setdefault("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

onboarding_routes = Blueprint('onboarding_routes', __name__)

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
CONFIDENCE_THRESHOLD = 90
CONFIDENCE_INCREMENT = 15
MAX_QUESTIONS_PER_SESSION = 20
SEVERITY_SCORE_THRESHOLD = 9
MAX_TOKENS = 400
TEMPERATURE = 0.7

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

        # Check authentication
        authenticated = True
        try:
            verify_jwt_in_request()
            if str(get_jwt_identity()) != str(user_id):
                return jsonify({"error": "Unauthorized user ID."}), 403
        except:
            authenticated = False

        user = User.query.get(user_id)
        if not user and authenticated:
            return jsonify({"error": "User not found"}), 404

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

        # Only store for authenticated premium users
        logged_symptom = None
        if authenticated and user and user.subscription_tier == UserTierEnum.PAID:
            try:
                new_log = SymptomLog(
                    user_id=user_id,
                    symptom_name=initial_symptom,
                    notes=previous_answers,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_log)
                db.session.commit()
                logged_symptom = {
                    "id": new_log.id,
                    "symptom": new_log.symptom_name,
                    "notes": new_log.notes,
                    "timestamp": new_log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                }
            except Exception as db_error:
                logger.error(f"Database error: {str(db_error)}")
                db.session.rollback()
                return jsonify({"error": "Error saving symptom information"}), 500
        else:
            logger.info(f"Onboarding data (unauthenticated/non-premium user {user_id}): {data}")

        system_instruction = (
            "You are a knowledgeable medical assistant guiding a patient through diagnostic questions. "
            "Ask one specific follow-up question at a time. Avoid repeated questions on the same topic unless necessary. "
            "For chest pain, shortness of breath, or cardiovascular symptoms, prioritize questions about heart-related conditions. "
            "For symptoms like dizziness or headache, ask about environmental factors like heat exposure."
        )
        prompt = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"The patient mentioned: '{initial_symptom}'.\nDetails so far: '{previous_answers}'.\nWhat is a relevant follow-up question?"}
        ]

        next_question = call_openai_api(prompt, max_tokens=MAX_TOKENS)
        next_question = ensure_single_question(next_question)

        return jsonify({
            "next_question": next_question,
            "question_count": question_count + 1,
            "confidence_score": confidence_score,
            "logged_symptom": logged_symptom if logged_symptom else None
        })

    except Exception as e:
        logger.error(f"Error during onboarding: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Unexpected error during onboarding."}), 500