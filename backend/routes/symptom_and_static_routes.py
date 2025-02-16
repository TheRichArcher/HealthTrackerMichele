from flask import Blueprint, request, jsonify, send_from_directory
from extensions import db
from models import SymptomLog
from datetime import datetime
import logging
import openai
import os
import re

# Logger setup
logger = logging.getLogger("symptom_routes")

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
            messages = [{
                "role": "system",
                "content": """You are HealthTracker AI, an advanced medical screening assistant.

CONVERSATION GUIDELINES:
- Listen carefully to the patient's description
- Ask natural follow-up questions based on what they tell you
- Focus on the most relevant symptoms first
- Gather key information through conversation:
  * Timing/duration when relevant
  * Severity when needed
  * Specific triggers or patterns
  * Associated symptoms
  * Impact on daily activities

DIAGNOSTIC APPROACH:
- Primary Condition assessment (50-98% confidence based on certainty)
- Alternative possibilities with explanations
- Triage levels (mild/moderate/severe) based on symptoms

🚨 EMERGENCY PROTOCOL:
- If symptoms suggest immediate danger (chest pain, breathing difficulty, severe confusion):
  * Immediately recommend emergency care
  * Skip normal conversation flow

CRITICAL RULES:
- Ask ONLY ONE question at a time and wait for the patient's response
- Maintain a natural, conversational tone
- Ask questions that flow logically from patient responses
- Include appropriate medical disclaimers
- Never provide definitive medical diagnosis
- Clearly explain reasoning for recommendations"""
            }]
            messages.extend(conversation_history)
            messages.append({"role": "user", "content": symptoms})

            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=messages,
                temperature=0.7,
                max_tokens=750
            )

            # Validate OpenAI response
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("Invalid response from OpenAI")

            ai_response = response.choices[0].message.content
            triage_level = determine_triage_level(ai_response, symptoms)

            # Determine confidence score
            confidence = 50  # Default confidence
            if "multiple possible conditions" in ai_response.lower():
                confidence = 75
            elif "most likely" in ai_response.lower():
                confidence = 85
            elif "very likely" in ai_response.lower():
                confidence = 95
            elif "clear, definitive diagnosis" in ai_response.lower():
                confidence = 98

            logger.info(f"Analyzed symptoms: {symptoms[:50]}... Triage Level: {triage_level}, Confidence: {confidence}%")

            return jsonify({
                'possible_conditions': ai_response,
                'triage_level': triage_level,
                'confidence': confidence
            })

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