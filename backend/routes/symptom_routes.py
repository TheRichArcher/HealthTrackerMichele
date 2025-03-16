from flask import Blueprint, request, jsonify, current_app
from backend.models import db, SymptomLog
import openai
import os
from datetime import datetime
import uuid
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from backend.utils.auth import generate_temp_user_id, token_required  # Add token_required import
from backend.utils.pdf_generator import generate_pdf_report

symptom_routes = Blueprint('symptom_routes', __name__)

# Configure OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Retry decorator for OpenAI API calls
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(openai.OpenAIError))
def call_openai_api(messages):
    try:
        response = openai.ChatCompletion.create(
            model=os.getenv('OPENAI_MODEL', 'gpt-4o'),
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )
        return response
    except openai.OpenAIError as e:
        logger.error(f"OpenAI API call failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in OpenAI API call: {str(e)}")
        raise

@symptom_routes.route('/symptoms/analyze', methods=['POST'])
def analyze_symptoms():
    try:
        data = request.get_json()
        symptom = data.get('symptom')
        conversation_history = data.get('conversation_history', [])

        # Validate incoming request
        if not symptom or not isinstance(symptom, str):
            return jsonify({'error': 'Valid symptom is required'}), 400
        if not isinstance(conversation_history, list):
            return jsonify({'error': 'Conversation history must be a list'}), 400

        # Prepare the conversation for OpenAI
        messages = [
            {"role": "system", "content": "You are a medical AI assistant. Provide accurate, concise symptom analysis. Always include possible condition name(s) and confidence percentage (e.g., 'Possible Condition: Headache (Cephalgia), Confidence: 85%'). Do not offer a final assessment until you are 95% confident. If less than 95% confident, ask clarifying questions and include possible conditions. When confident (≥95%), include condition name (common and medical terms if available), confidence percentage, triage level (AT_HOME, MODERATE, SEVERE), and care recommendation."}
        ]

        # Add conversation history
        for msg in conversation_history:
            if not isinstance(msg, dict) or 'message' not in msg or 'isBot' not in msg:
                return jsonify({'error': 'Invalid conversation history format'}), 400
            role = "assistant" if msg['isBot'] else "user"
            messages.append({"role": role, "content": msg['message']})

        # Add the latest user input
        messages.append({"role": "user", "content": symptom})

        # Call OpenAI API with retry logic
        response = call_openai_api(messages)
        bot_response = response.choices[0].message['content']

        # Parse the response
        is_assessment = "Confidence:" in bot_response and float(bot_response.split("Confidence:")[1].split("%")[0].strip()) >= 95
        requires_upgrade = is_assessment  # Set to true for high-confidence assessments

        response_data = {
            'response': bot_response,
            'is_assessment': is_assessment,
            'requires_upgrade': requires_upgrade
        }

        if is_assessment or "Possible Condition:" in bot_response:
            # Extract or default values
            if is_assessment:
                condition_common = bot_response.split("Condition:")[1].split("(")[0].strip() if "Condition:" in bot_response else "Unknown"
                condition_medical = bot_response.split("(")[1].split(")")[0].strip() if "(" in bot_response and ")" in bot_response else "N/A"
                confidence = float(bot_response.split("Confidence:")[1].split("%")[0].strip())
                triage_level = bot_response.split("Triage Level:")[1].split("\n")[0].strip() if "Triage Level:" in bot_response else "MODERATE"
                care_recommendation = bot_response.split("Care Recommendation:")[1].strip() if "Care Recommendation:" in bot_response else "Consider consulting a healthcare provider."
            else:
                # For low-confidence responses, extract possible condition and confidence
                possible_condition = bot_response.split("Possible Condition:")[1].split(",")[0].strip() if "Possible Condition:" in bot_response else "Unknown"
                confidence = float(bot_response.split("Confidence:")[1].split("%")[0].strip()) if "Confidence:" in bot_response else 0
                condition_medical = "N/A"
                triage_level = "N/A"
                care_recommendation = "Please provide more details to refine the assessment."

            # Store assessment in SymptomLog
            symptom_log = SymptomLog(
                user_id=generate_temp_user_id(request),  # Placeholder; should come from auth context
                symptom=symptom,
                response=bot_response,
                confidence=confidence,
                condition_common=condition_common,
                condition_medical=condition_medical,
                triage_level=triage_level,
                care_recommendation=care_recommendation,
                created_at=datetime.utcnow()
            )
            db.session.add(symptom_log)
            db.session.commit()

            response_data.update({
                'condition_common': condition_common,
                'condition_medical': condition_medical,
                'confidence': confidence,
                'triage_level': triage_level,
                'care_recommendation': care_recommendation,
                'assessment_id': symptom_log.id
            })

        return jsonify({'response': response_data}), 200

    except openai.OpenAIError as e:
        logger.error(f"OpenAI API error: {str(e)} - Retrying...")
        return jsonify({'error': 'Temporary API issue, retrying...'}), 500
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error analyzing symptoms: {str(e)} - Request data: {data}")
        return jsonify({'response': 'Error processing your request. Please try again.'}), 500

@symptom_routes.route('/history', methods=['GET'])
@token_required
def get_history(current_user=None):
    try:
        if not current_user:
            return jsonify({'error': 'Authentication required'}), 401

        user_id = current_user['user_id']
        symptom_logs = SymptomLog.query.filter_by(user_id=user_id).order_by(SymptomLog.created_at.desc()).all()
        history = [{
            'id': log.id,
            'symptom': log.symptom,
            'response': log.response,
            'confidence': log.confidence,
            'condition_common': log.condition_common,
            'condition_medical': log.condition_medical,
            'triage_level': log.triage_level,
            'care_recommendation': log.care_recommendation,
            'created_at': log.created_at.isoformat()
        } for log in symptom_logs]

        return jsonify({'history': history}), 200
    except Exception as e:
        logger.error(f"Error fetching history: {str(e)} - User ID: {current_user['user_id'] if current_user else 'None'}")
        return jsonify({'error': 'Failed to fetch history'}), 500

@symptom_routes.route('/doctor-report/<int:assessment_id>', methods=['GET'])
@token_required
def get_doctor_report(current_user=None, assessment_id=None):
    try:
        if not current_user:
            return jsonify({'error': 'Authentication required'}), 401

        symptom_log = SymptomLog.query.get_or_404(assessment_id)
        if symptom_log.user_id != current_user['user_id']:
            return jsonify({'error': 'Unauthorized access'}), 403

        report_data = {
            'user_id': current_user['user_id'],
            'timestamp': datetime.utcnow().isoformat(),
            'condition_common': symptom_log.condition_common,
            'condition_medical': symptom_log.condition_medical,
            'confidence': symptom_log.confidence,
            'triage_level': symptom_log.triage_level,
            'care_recommendation': symptom_log.care_recommendation
        }
        report_url = generate_pdf_report(report_data)
        return jsonify({'report_url': report_url}), 200
    except Exception as e:
        logger.error(f"Error generating doctor report: {str(e)} - Assessment ID: {assessment_id}, User ID: {current_user['user_id'] if current_user else 'None'}")
        return jsonify({'error': 'Failed to generate report'}), 500