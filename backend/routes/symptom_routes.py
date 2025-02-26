from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware import require_auth
from backend.routes.extensions import db
from backend.models import User, Symptom, Report
from backend.routes.openai_config import SYSTEM_PROMPT, clean_ai_response
import openai
import os
import json
import logging
import time
import re
from datetime import datetime
from typing import Any
from flask_jwt_extended import get_jwt_identity

# Blueprint setup
symptom_routes = Blueprint('symptom_routes', __name__)

# Constants
MAX_INPUT_LENGTH = 1000
DEFAULT_TEMPERATURE = 0.7
MAX_TOKENS = 800
MODEL_NAME = "gpt-4-turbo-preview"
MAX_RETRIES = 3
RETRY_DELAY = 2

class TriageLevel:
    MILD = "MILD"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"

def sanitize_input(text: str) -> str:
    """Sanitize user input by removing excess whitespace and special characters."""
    if not isinstance(text, str):
        return ""
    text = " ".join(text.split())
    text = re.sub(r'[^a-zA-Z0-9\s.,!?-]', '', text)
    return text[:MAX_INPUT_LENGTH]

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
        current_app.logger.warning("Emergency condition detected in symptoms")
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

# Fix: Call require_auth() to get the actual decorator
@symptom_routes.route('/analyze', methods=['POST'])
@require_auth()  # Note the parentheses - this calls the function to get the decorator
def analyze_symptoms():
    user_id = get_jwt_identity()  # Use get_jwt_identity() instead of g.user_id
    data = request.json
    
    if not data or 'symptom' not in data:
        return jsonify({'error': 'No symptom provided'}), 400
    
    symptom_text = sanitize_input(data['symptom'])
    conversation_history = data.get('conversation_history', [])
    
    # Log the incoming request
    current_app.logger.info(f"Analyzing symptom: {symptom_text}")
    current_app.logger.info(f"Conversation history length: {len(conversation_history)}")
    
    try:
        # Prepare the conversation for OpenAI
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # Add conversation history
        for entry in conversation_history:
            role = "assistant" if entry.get("isBot", False) else "user"
            content = entry.get("message", "")
            current_app.logger.debug(f"Adding message to history - Role: {role}, Content: {content[:50]}...")
            messages.append({"role": role, "content": content})
        
        # Add the current symptom if not already in conversation
        if not conversation_history or conversation_history[-1].get("isBot", False):
            messages.append({"role": "user", "content": symptom_text})
        
        current_app.logger.info(f"Sending {len(messages)} messages to OpenAI")
        
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Try with retries for handling rate limits and temporary errors
        for attempt in range(MAX_RETRIES):
            try:
                # Call OpenAI API
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    temperature=DEFAULT_TEMPERATURE,
                    max_tokens=MAX_TOKENS
                )
                
                # Extract and process the response
                ai_response = response.choices[0].message.content
                current_app.logger.info(f"Raw OpenAI response: {ai_response}")
                
                # Process the response to determine if it's a question or assessment
                processed_response = clean_ai_response(ai_response)
                
                # If it's an assessment, enhance with triage level determination
                if isinstance(processed_response, dict) and processed_response.get('is_assessment'):
                    current_app.logger.info(f"Processed response type: assessment")
                    
                    # If triage level isn't already set, determine it based on symptoms and response
                    if not processed_response.get('assessment', {}).get('triage_level'):
                        triage_level = determine_triage_level(ai_response, symptom_text)
                        if 'assessment' in processed_response:
                            processed_response['assessment']['triage_level'] = triage_level
                    
                    current_app.logger.debug(f"Assessment details: {json.dumps(processed_response)[:200]}...")
                else:
                    current_app.logger.info(f"Processed response type: question")
                    current_app.logger.debug(f"Question: {processed_response if isinstance(processed_response, str) else processed_response.get('question', '')}")
                
                # Save the interaction to the database
                save_symptom_interaction(user_id, symptom_text, processed_response)
                
                return jsonify(processed_response)
                
            except openai.RateLimitError as e:
                current_app.logger.error(f"OpenAI rate limit exceeded (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return jsonify({'error': 'AI service is temporarily busy. Please try again later.'}), 429
                time.sleep(RETRY_DELAY * (attempt + 2))  # Longer delay for rate limits

            except openai.APIConnectionError as e:
                current_app.logger.error(f"OpenAI API connection error (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return jsonify({'error': 'Unable to connect to AI service. Please try again later.'}), 503
                time.sleep(RETRY_DELAY * (attempt + 1))

            except openai.APIError as e:
                current_app.logger.error(f"OpenAI API error (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return jsonify({'error': 'AI service error. Please try again later.'}), 500
                time.sleep(RETRY_DELAY * (attempt + 1))

            except openai.AuthenticationError as e:
                current_app.logger.error(f"OpenAI authentication error: {e}")
                return jsonify({'error': 'AI service configuration error.'}), 500

            except openai.InvalidRequestError as e:
                current_app.logger.error(f"OpenAI invalid request error: {e}")
                return jsonify({'error': 'Invalid request to AI service.'}), 400
                
            except Exception as e:
                current_app.logger.error(f"Unexpected error (attempt {attempt + 1}): {e}", exc_info=True)
                if attempt == MAX_RETRIES - 1:
                    return jsonify({'error': 'Unable to process your request.'}), 500
                time.sleep(RETRY_DELAY)
        
        return jsonify({'error': 'Maximum retries reached with AI service.'}), 500
        
    except Exception as e:
        current_app.logger.error(f"Error analyzing symptoms: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

def save_symptom_interaction(user_id, symptom_text, response_data):
    """Save the symptom interaction to the database"""
    try:
        # Create a new symptom record
        new_symptom = Symptom(
            user_id=user_id,
            description=symptom_text,
            response=json.dumps(response_data) if isinstance(response_data, dict) else response_data,
            created_at=datetime.utcnow()
        )
        db.session.add(new_symptom)
        db.session.commit()
        
        # If this is an assessment with conditions, create a report
        if isinstance(response_data, dict) and response_data.get('is_assessment') and 'assessment' in response_data:
            assessment = response_data['assessment']
            conditions = assessment.get('conditions', [])
            
            if conditions:
                # Create a report for this assessment
                new_report = Report(
                    user_id=user_id,
                    symptom_id=new_symptom.id,
                    content=json.dumps(assessment),
                    created_at=datetime.utcnow()
                )
                db.session.add(new_report)
                db.session.commit()
                current_app.logger.info(f"Created report for assessment with ID: {new_report.id}")
                
        return True
    except Exception as e:
        current_app.logger.error(f"Error saving symptom interaction: {str(e)}", exc_info=True)
        db.session.rollback()
        return False

# Fix: Call require_auth() to get the actual decorator
@symptom_routes.route('/history', methods=['GET'])
@require_auth()  # Note the parentheses - this calls the function to get the decorator
def get_symptom_history():
    user_id = get_jwt_identity()  # Use get_jwt_identity() instead of g.user_id
    
    try:
        # Get the user's symptom history
        symptoms = Symptom.query.filter_by(user_id=user_id).order_by(Symptom.created_at.desc()).all()
        
        result = []
        for symptom in symptoms:
            try:
                response_data = json.loads(symptom.response) if symptom.response else {}
                
                # Format the response based on whether it's an assessment or question
                if isinstance(response_data, dict) and response_data.get('is_assessment'):
                    assessment = response_data.get('assessment', {})
                    conditions = assessment.get('conditions', [])
                    condition_names = [c.get('name') for c in conditions if c.get('name')]
                    
                    result.append({
                        'id': symptom.id,
                        'description': symptom.description,
                        'created_at': symptom.created_at.isoformat(),
                        'is_assessment': True,
                        'conditions': condition_names,
                        'triage_level': assessment.get('triage_level')
                    })
                else:
                    # It's a question or unstructured response
                    question = response_data.get('question') if isinstance(response_data, dict) else str(response_data)
                    result.append({
                        'id': symptom.id,
                        'description': symptom.description,
                        'created_at': symptom.created_at.isoformat(),
                        'is_assessment': False,
                        'response': question
                    })
            except Exception as e:
                current_app.logger.error(f"Error processing symptom {symptom.id}: {str(e)}")
                # Include a basic entry even if processing failed
                result.append({
                    'id': symptom.id,
                    'description': symptom.description,
                    'created_at': symptom.created_at.isoformat(),
                    'error': 'Failed to process response'
                })
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error retrieving symptom history: {str(e)}")
        return jsonify({'error': str(e)}), 500