from flask import Blueprint, request, jsonify, send_from_directory
from backend.routes.extensions import db
from backend.models import SymptomLog
from datetime import datetime
import logging
import openai
import os
import re
from backend.routes.openai_config import SYSTEM_PROMPT, clean_ai_response

# Logger setup
logger = logging.getLogger("symptom_routes")
logger.setLevel(logging.DEBUG)  # Enable debug logging

# Blueprint setup
symptom_routes = Blueprint("symptom_routes", __name__)

def sanitize_input(text):
    """Sanitize user input by removing excess whitespace and special characters."""
    if not isinstance(text, str):
        return ""
    # Remove excess whitespace
    text = " ".join(text.split())
    # Remove special characters except basic punctuation
    text = re.sub(r'[^a-zA-Z0-9\s.,!?-]', '', text)
    # Limit length to 1000 characters
    return text[:1000]

@symptom_routes.route("/", methods=["POST", "GET"])
def symptoms():
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

            logger.info(f"Symptom logged: {symptom_name} (User {user_id})")
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
            logger.error(f"Error logging symptom: {e}")
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
        logger.error(f"Error retrieving symptoms: {e}")
        return jsonify({"error": "Failed to retrieve symptoms"}), 500

def determine_triage_level(ai_response, symptoms):
    """Determine appropriate triage level based on symptoms and AI response."""
    response_lower = ai_response.lower()
    symptoms_lower = symptoms.lower()

    # Emergency conditions that require immediate attention
    emergency_terms = [
        "chest pain", "difficulty breathing", "shortness of breath",
        "severe allergic reaction", "anaphylaxis", "unconscious",
        "stroke", "heart attack", "severe bleeding", "head injury"
    ]
    if any(term in response_lower for term in emergency_terms):
        return "severe"

    # Mild conditions that can typically be managed at home
    mild_conditions = [
        ('allergy', ['cat', 'dust', 'pollen', 'sneez']),
        ('cold', ['runny nose', 'sore throat', 'cough']),
        ('minor', ['headache', 'muscle ache']),
        ('common', ['tired', 'fatigue'])
    ]

    for condition, symptoms_list in mild_conditions:
        if condition in symptoms_lower or any(s in symptoms_lower for s in symptoms_list):
            if not any(emergency in response_lower for emergency in emergency_terms):
                return "mild"

    return "moderate"

@symptom_routes.route("/analyze", methods=["POST"])
def analyze_symptoms():
    """Handle AI analysis of symptoms."""
    try:
        data = request.get_json()
        symptoms = sanitize_input(data.get('symptoms', ''))
        conversation_history = data.get('conversation_history', [])

        if not symptoms:
            return jsonify({
                'possible_conditions': "Please describe your symptoms.",
                'triage_level': 'moderate',
                'confidence': 50
            }), 400

        # Validate OpenAI API key
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            logger.error("OpenAI API key is missing")
            return jsonify({
                'possible_conditions': "AI service is temporarily unavailable.",
                'triage_level': 'moderate',
                'confidence': 50
            }), 503

        try:
            client = openai.OpenAI(api_key=openai_api_key)
            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                }
            ]
            messages.extend(conversation_history)
            messages.append({"role": "user", "content": symptoms})

            logger.debug("🚀 Sending request to OpenAI with messages: %s", messages)

            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=messages,
                temperature=0.7,
                max_tokens=750
            )

            # Validate OpenAI response with improved logging
            if not response.choices or not response.choices[0].message.content:
                logger.error(f"Invalid OpenAI response: {response}")
                raise ValueError("Invalid response from OpenAI")

            # Log raw response for debugging
            raw_response = response.choices[0].message.content
            logger.debug("📝 Raw OpenAI response: %s", raw_response)

            # Clean the response and log the result
            ai_response = clean_ai_response(raw_response)
            logger.debug("🧹 Cleaned response: %s", ai_response)

            # Double-check for any remaining asterisks
            if '*' in ai_response:
                logger.warning("⚠️ Asterisks found after cleaning: %s", ai_response)
                ai_response = ai_response.replace('*', '')
                logger.debug("🔄 Response after asterisk removal: %s", ai_response)

            triage_level = determine_triage_level(ai_response, symptoms)
            logger.debug("🏥 Determined triage level: %s", triage_level)

            # Determine confidence score with improved logging
            confidence = None
            if "clear diagnosis" in ai_response.lower():
                confidence = 95
                logger.debug("💯 Clear diagnosis - confidence: 95%")
            elif "very likely" in ai_response.lower():
                confidence = 90
                logger.debug("📈 Very likely - confidence: 90%")
            elif "most likely" in ai_response.lower():
                confidence = 85
                logger.debug("📊 Most likely - confidence: 85%")
            else:
                confidence = 75
                logger.debug("📉 Default confidence: 75%")

            # Final response check
            final_response = {
                'possible_conditions': ai_response,
                'triage_level': triage_level,
                'confidence': confidence
            }
            logger.debug("📤 Sending final response: %s", final_response)

            return jsonify(final_response)

        except openai.APIError as e:
            logger.error(f"OpenAI API Error: {e}")
            return jsonify({
                'possible_conditions': "AI service is temporarily unavailable.",
                'triage_level': 'moderate',
                'confidence': 50
            }), 503

    except Exception as e:
        logger.error(f'Error analyzing symptoms: {e}')
        return jsonify({
            'possible_conditions': "I apologize, but I'm having trouble processing your request right now. Please try again or seek medical attention if you're concerned about your symptoms.",
            'triage_level': 'moderate',
            'confidence': 50
        }), 500

@symptom_routes.route('/<path:filename>')
def serve_static(filename):
    """Serve static files."""
    static_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'dist')

    # Validate file exists before serving
    file_path = os.path.join(static_folder, filename)
    if not os.path.exists(file_path):
        logger.error(f"Static file not found: {filename}")
        return jsonify({"error": "File not found"}), 404

    return send_from_directory(static_folder, filename)