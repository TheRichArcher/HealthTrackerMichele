from flask import Blueprint, request, jsonify
from extensions import db
from models import SymptomLog
from datetime import datetime
import openai
import logging
import time
import re

# Logger setup
logger = logging.getLogger("onboarding_routes")

# Blueprint setup
onboarding_routes = Blueprint('onboarding_routes', __name__)

# Configuration
CONFIDENCE_THRESHOLD = 90
CONFIDENCE_INCREMENT = 15
MAX_QUESTIONS_PER_SESSION = 20
RETRY_DELAY = 2
MAX_RETRIES = 3
SEVERITY_SCORE_THRESHOLD = 9

# Emergency Keywords
EMERGENCY_KEYWORDS = [
    "chest pain", "shortness of breath", "tightness", "weakness", "slurred speech", "fainting",
    "vision loss", "abnormal heartbeat", "numbness", "severe headache"
]

# Normalize vague time phrases
def normalize_time_phrases(response: str) -> str:
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

# Check for emergency symptoms
def check_for_emergency(symptom_text: str, severity_score: int) -> bool:
    count = sum(1 for keyword in EMERGENCY_KEYWORDS if keyword.lower() in symptom_text.lower())
    return count >= 2 or severity_score >= SEVERITY_SCORE_THRESHOLD

# OpenAI API Request Function
def send_openai_request(prompt: str) -> str:
    fallback_question = "Can you provide more details?"

    for attempt in range(MAX_RETRIES):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "system", "content": "You are a medical assistant helping with symptom analysis."},
                          {"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.7
            )
            response_text = response['choices'][0]['message']['content'].strip()
            return response_text if response_text else fallback_question
        except openai.OpenAIError as api_error:
            logger.error(f"OpenAI API Error (Attempt {attempt + 1}): {api_error}")
            time.sleep(RETRY_DELAY)

    return fallback_question

# Ensure a single, unique question
def ensure_single_question(response_text: str) -> str:
    questions = [q.strip() for q in response_text.split('?') if q.strip()]
    return questions[0] + "?" if questions else "Can you provide more information?"

# Onboarding Route
@onboarding_routes.route("/api/onboarding", methods=["POST"])
def onboarding():
    """Handles user onboarding for symptom tracking and analysis."""
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        initial_symptom = data.get("initial_symptom", "").strip().lower()
        previous_answers = normalize_time_phrases(data.get("previous_answers", "").strip())
        question_count = int(data.get("question_count", 0))
        confidence_score = int(data.get("confidence_score", 0))

        logger.info(f"Onboarding request - User ID: {user_id}, Symptom: '{initial_symptom}', Confidence: {confidence_score}")

        # Limit questions per session
        if question_count >= MAX_QUESTIONS_PER_SESSION:
            return jsonify({"next_question": "Onboarding complete! Thank you for your patience."})

        # Check for emergency symptoms
        if check_for_emergency(initial_symptom + " " + previous_answers, confidence_score):
            return jsonify({"next_question": "Your symptoms may indicate a serious issue. Seek immediate medical attention."})

        # Confidence-based early termination
        if confidence_score >= CONFIDENCE_THRESHOLD:
            return jsonify({"next_question": "Onboarding complete! We've gathered enough information."})

        # Log symptom in database
        try:
            new_log = SymptomLog(
                user_id=user_id,
                symptom=initial_symptom,
                notes=previous_answers,
                date=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
            logger.info(f"Symptom logged: {initial_symptom} (User {user_id})")
        except Exception as db_error:
            db.session.rollback()
            logger.error(f"Database Error: {db_error}")
            return jsonify({"error": "Failed to log symptom."}), 500

        # Generate the next question
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
                "symptom": new_log.symptom,
                "notes": new_log.notes,
                "date": new_log.date.strftime("%Y-%m-%d %H:%M:%S")
            }
        })

    except Exception as e:
        logger.error(f"Unexpected error during onboarding: {str(e)}")
        return jsonify({"error": "An unexpected error occurred during onboarding."}), 500
