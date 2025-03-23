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
    level=logging.INFO
)

logger = logging.getLogger("onboarding_routes")
onboarding_routes = Blueprint("onboarding_routes", __name__, url_prefix="/onboarding")

# Configuration
CONFIDENCE_THRESHOLD = 0.9  # Confidence threshold for stopping questioning
MAX_QUESTIONS_PER_SESSION = 10  # Maximum questions to ask in one session

def check_for_emergency(user_input):
    """Check if user input contains emergency keywords."""
    emergency_keywords = [
        "chest pain", "difficulty breathing", "severe bleeding", "unconscious", 
        "seizure", "sudden numbness", "severe allergic reaction", "anaphylaxis"
    ]
    for keyword in emergency_keywords:
        if re.search(keyword, user_input.lower()):
            return True, f"Emergency detected: {keyword}"
    return False, None

def generate_diagnostic_question(history):
    """Generate the next diagnostic question using OpenAI."""
    history_text = "\n".join([f"Q: {q}\nA: {a}" for q, a in history])
    prompt = [
        {"role": "system", "content": "You are a medical assistant. Based on the conversation history, ask the next diagnostic question to narrow down the possible condition. Respond with only the question."},
        {"role": "user", "content": f"Conversation history:\n{history_text}\n\nWhat is the next question to ask?"}
    ]
    try:
        question = call_openai_api(prompt, max_tokens=50)
        return question.strip()
    except Exception as e:
        logger.error(f"Failed to generate diagnostic question: {str(e)}", exc_info=True)
        return "Can you describe your symptoms in more detail?"

def assess_confidence(history):
    """Assess confidence in the diagnosis based on conversation history."""
    history_text = "\n".join([f"Q: {q}\nA: {a}" for q, a in history])
    prompt = [
        {"role": "system", "content": "You are a medical assistant. Based on the conversation history, provide a confidence score (0.0 to 1.0) for your current understanding of the patient's condition."},
        {"role": "user", "content": f"Conversation history:\n{history_text}\n\nWhat is your confidence score?"}
    ]
    try:
        response = call_openai_api(prompt, max_tokens=10)
        confidence = float(response.strip())
        return min(max(confidence, 0.0), 1.0)  # Ensure confidence is between 0 and 1
    except Exception as e:
        logger.error(f"Failed to assess confidence: {str(e)}", exc_info=True)
        return 0.5  # Default to moderate confidence if assessment fails

@onboarding_routes.route("/", methods=["POST"])
def guide_user():
    """Guide the user through a diagnostic question process."""
    try:
        # Verify JWT token if present
        user_id = None
        try:
            verify_jwt_in_request()
            user_id = get_jwt_identity()
        except Exception as e:
            logger.debug(f"No valid JWT token provided: {str(e)}")

        data = request.get_json()
        user_input = data.get("user_input", "").strip()
        session_id = data.get("session_id")
        history = data.get("history", [])  # List of [question, answer] pairs

        if not user_input or not session_id:
            return jsonify({"error": "user_input and session_id are required."}), 400

        # Check for emergency situations
        is_emergency, emergency_reason = check_for_emergency(user_input)
        if is_emergency:
            logger.warning(f"Emergency detected for session {session_id}: {emergency_reason}")
            return jsonify({
                "emergency": True,
                "message": "This sounds like a medical emergency. Please seek immediate medical attention.",
                "reason": emergency_reason
            }), 200

        # Add the latest user input to history
        if history and len(history) > 0 and history[-1][1] is None:
            history[-1][1] = user_input
        else:
            # This should not happen if the client is behaving correctly
            logger.warning(f"Unexpected history state for session {session_id}: {history}")
            return jsonify({"error": "Invalid history state."}), 400

        # Assess confidence in the diagnosis
        confidence_score = assess_confidence(history)
        question_count = len(history)

        # Log confidence and question count
        logger.info(f"Session {session_id}: confidence_score={confidence_score:.2f}, question_count={question_count}")

        # Check if we should stop asking questions
        if confidence_score >= CONFIDENCE_THRESHOLD or question_count >= MAX_QUESTIONS_PER_SESSION:
            logger.info(f"Stopping onboarding for session {session_id}: confidence={confidence_score:.2f}, questions asked={question_count}")
            return jsonify({
                "complete": True,
                "message": "Thank you for providing the information. A report will be generated shortly.",
                "confidence": confidence_score
            }), 200

        # Generate the next question
        next_question = generate_diagnostic_question(history)
        history.append([next_question, None])

        # Log the symptom for premium users
        if user_id:
            user = User.query.get(user_id)
            if user and user.subscription_tier == UserTierEnum.PAID.value:
                symptom_log = SymptomLog(
                    user_id=user_id,
                    symptom=user_input,
                    created_at=datetime.utcnow()
                )
                db.session.add(symptom_log)
                db.session.commit()
                logger.info(f"Symptom logged for user {user_id}: {user_input}")
            else:
                logger.debug(f"User {user_id} is not a premium user, skipping symptom logging")

        return jsonify({
            "question": next_question,
            "session_id": session_id,
            "history": history,
            "confidence": confidence_score
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in onboarding process for session {session_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "An error occurred during the onboarding process."}), 500