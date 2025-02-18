from flask import Blueprint, request, jsonify, send_from_directory
from backend.routes.extensions import db
from backend.models import SymptomLog
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

def format_ai_response(response_text):
    """Format the AI response to remove markdown and structure the message properly."""
    # Remove unwanted formatting
    clean_text = re.sub(r'\*\*|Possible Conditions:|Confidence Level:|Care Recommendation:', '', response_text)
    
    # Normalize spaces and remove unnecessary newlines
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    return clean_text

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
                "content": """You are Michele, a knowledgeable medical assistant. 
Respond naturally and conversationally as if speaking directly to the patient.
Focus on understanding their symptoms and asking relevant follow-up questions.

Important guidelines:
1. Start responses with phrases like "Based on what you've described..." or "I understand that..."
2. Ask only one follow-up question at a time
3. Keep responses direct and conversational
4. Never use any special formatting or markdown
5. Never use headers or labels
6. Never mention confidence levels or care recommendations in your response
7. Focus solely on understanding and discussing the symptoms

Example response:
"I understand you're experiencing [symptom]. Can you tell me how long this has been happening?"

Remember: Always maintain a natural conversation flow without any special formatting."""
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

            # Log raw response for debugging
            raw_response = response.choices[0].message.content
            logger.info(f"Raw AI Response: {raw_response}")

            # Clean and format the response
            ai_response = format_ai_response(raw_response)
            triage_level = determine_triage_level(ai_response, symptoms)

            # Enhanced confidence scoring with improved structure
            response_lower = ai_response.lower()
            confidence_levels = [
                (["several possibilities", "could be various", "multiple conditions",
                  "not enough information", "need more details", "unclear", 
                  "can't be certain", "difficult to determine"], 65),

                (["most likely", "probably", "suggests", "indicates", 
                  "appears to be", "may be", "could be"], 80),

                (["one main condition", "clear indication", "strongly suggests", 
                  "very likely", "typical presentation of", "characteristic of", 
                  "definitive signs", "consistent with"], 95),

                (["clear, definitive diagnosis", "conclusive evidence", 
                  "definitive presentation", "certain", "absolutely clear"], 98)
            ]

            confidence = 50  # Default
            for phrases, score in confidence_levels:
                if any(phrase in response_lower for phrase in phrases):
                    confidence = score
                    break  # Stop checking once the highest match is found

            # Set reasonable fallback confidence with explicit logging
            if confidence == 50:
                confidence = 75
                logger.info("No confidence keywords matched. Setting default confidence to 75%.")

            # Enhanced logging with more response context
            logger.info(
                f"Analyzed symptoms: {symptoms[:50]}... "
                f"AI Response: {ai_response[:100]}... "
                f"Triage Level: {triage_level}, "
                f"Confidence: {confidence}%"
            )

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