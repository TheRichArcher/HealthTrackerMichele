from flask import Blueprint, request, jsonify, current_app, session
from backend.routes.extensions import db
from backend.models import User, Symptom, Report, UserTierEnum
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
import openai
import os
import json
import logging
import time
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from backend.routes.openai_config import SYSTEM_PROMPT, clean_ai_response, MIN_CONFIDENCE_THRESHOLD

# Blueprint setup
symptom_routes = Blueprint('symptom_routes', __name__)

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_DETAILED_EXCHANGES = 5  # Number of recent exchanges to keep in full detail
QUESTION_COUNT_THRESHOLD = 3  # Minimum number of questions before assessment

class UserTier:
    FREE = "free"  # Nurse Mode
    PAID = "pro"   # PA Mode - Updated to match UserTierEnum
    ONE_TIME = "one_time"  # Doctor's Report

@symptom_routes.route('/debug', methods=['GET'])
def debug_route():
    """Debug endpoint to check if our subscription enforcement logic is working"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Debug endpoint called")
    
    # Create a mock user with FREE tier
    class MockUser:
        def __init__(self):
            self.subscription_tier = UserTierEnum.FREE
    
    mock_user = MockUser()
    logger.info(f"Created mock user with tier: {mock_user.subscription_tier}")
    
    # Test medical recommendation detection
    test_response = "Please seek a consultation with a healthcare professional. Based on your symptoms, here are some possible conditions: Bacterial Conjunctivitis – 85%, Viral Conjunctivitis – 15%. Please seek a consultation with a healthcare professional. It's important to get a proper diagnosis as treatment can differ. Avoid touching your eyes and make sure to wash your hands frequently to prevent spread."
    
    logger.info(f"Testing with response: {test_response}")
    
    # Call clean_ai_response with the mock user
    processed = clean_ai_response(test_response, mock_user)
    logger.info(f"Processed response: {processed}")
    
    # Check if requires_upgrade is set
    requires_upgrade = processed.get('requires_upgrade', False)
    logger.info(f"Requires upgrade: {requires_upgrade}")
    
    return jsonify({
        'test_response': test_response,
        'processed': processed,
        'requires_upgrade': requires_upgrade,
        'user_tier': mock_user.subscription_tier.value if hasattr(mock_user.subscription_tier, 'value') else str(mock_user.subscription_tier)
    }), 200

@symptom_routes.route('/reset', methods=['POST'])
def reset_conversation():
    """Reset the conversation history"""
    return jsonify({"message": "Conversation reset successfully"}), 200

def prepare_messages_with_context(conversation_history, current_symptom, context_notes=None):
    """Prepare messages for OpenAI API with context preservation."""
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "system", 
            "content": "CRITICAL INSTRUCTION: Ask only ONE question at a time. Never combine multiple questions in a single message."
        },
        {
            "role": "system",
            "content": """CONTEXT AWARENESS REMINDER: 
            1. If the user says they "woke up with" a symptom, DO NOT ask how long they've had it.
            2. If the user mentions specific symptoms (like "crusty", "red", "itchy"), DO NOT ask if they have these exact symptoms.
            3. If you make a mistake and the user corrects you, acknowledge it and apologize briefly."""
        }
    ]
    
    # Count how many questions the AI has asked
    question_count = sum(1 for entry in conversation_history if entry.get("isBot", False) and "?" in entry.get("message", ""))
    
    # Extract all symptoms mentioned by the user so far
    user_symptoms = []
    for entry in conversation_history:
        if not entry.get("isBot", False):
            user_symptoms.append(entry.get("message", ""))
    
    if user_symptoms:
        # Create a summary of all user-reported symptoms
        symptom_summary = "User has reported: " + "; ".join(user_symptoms)
        messages.append({"role": "system", "content": symptom_summary})
    
    # If we have a long conversation history, create a summary of earlier exchanges
    if len(conversation_history) > MAX_DETAILED_EXCHANGES * 2:  # Each exchange has 2 messages
        early_history = conversation_history[:-(MAX_DETAILED_EXCHANGES * 2)]
        recent_history = conversation_history[-(MAX_DETAILED_EXCHANGES * 2):]
        
        # Add information about question count
        messages.append({
            "role": "system", 
            "content": f"You have asked {question_count} follow-up questions so far. Remember to ask at least {QUESTION_COUNT_THRESHOLD} questions before providing an assessment."
        })
        
        # Add recent history in full detail
        for entry in recent_history:
            role = "assistant" if entry.get("isBot", False) else "user"
            content = entry.get("message", "")
            messages.append({"role": role, "content": content})
    else:
        # If conversation is short, include all messages
        for entry in conversation_history:
            role = "assistant" if entry.get("isBot", False) else "user"
            content = entry.get("message", "")
            messages.append({"role": role, "content": content})
        
        # Add information about question count
        messages.append({
            "role": "system", 
            "content": f"You have asked {question_count} follow-up questions so far. Remember to ask at least {QUESTION_COUNT_THRESHOLD} questions before providing an assessment."
        })
    
    # Add the current symptom if not already in conversation
    if not conversation_history or conversation_history[-1].get("isBot", False):
        messages.append({"role": "user", "content": current_symptom})
    
    # Add context notes if provided
    if context_notes:
        messages.append({"role": "system", "content": f"CONTEXT NOTE: {context_notes}"})
    
    return messages, question_count

@symptom_routes.route('/analyze', methods=['POST'])
def analyze_symptoms():
    """Public endpoint for symptom analysis with tiered access."""
    # Check for JWT token to determine if user is authenticated and their tier
    auth_header = request.headers.get('Authorization')
    is_authenticated = False
    user_id = None
    current_user = None
    user_tier = UserTier.FREE  # Default to free tier (Nurse Mode)
    
    if auth_header and auth_header.startswith('Bearer '):
        try:
            # Optional JWT verification - if token exists and is valid, we'll save the history
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            is_authenticated = user_id is not None
            
            # In a real implementation, you would fetch the user's subscription tier from the database
            if is_authenticated:
                current_user = User.query.get(user_id)
                if current_user:
                    # Get subscription tier from the user object
                    user_tier = current_user.subscription_tier.value if hasattr(current_user, 'subscription_tier') else UserTier.FREE
                    current_app.logger.info(f"User {user_id} subscription tier: {user_tier}")
        except Exception as e:
            current_app.logger.warning(f"Invalid token provided: {str(e)}")
            # Continue as unauthenticated user
    
    # For unauthenticated users or if user not found, create a mock user with FREE tier
    if not current_user:
        current_app.logger.info("Creating mock FREE tier user for unauthenticated request")
        # Create a mock user object with FREE tier
        class MockUser:
            def __init__(self):
                self.subscription_tier = UserTierEnum.FREE
        
        current_user = MockUser()
        current_app.logger.info(f"Mock user created with tier: {current_user.subscription_tier}")
    
    try:
        data = request.get_json()
        symptoms = data.get('symptom', '')
        conversation_history = data.get('conversation_history', [])
        context_notes = data.get('context_notes', '')
        one_time_report = data.get('one_time_report', False)  # Flag for one-time Doctor's Report purchase
        reset = data.get('reset', False)  # Flag to reset conversation
        
        if reset:
            return jsonify({
                "message": "Conversation reset successfully",
                "possible_conditions": "Hello! I'm your AI medical assistant. Please describe your symptoms.",
                "is_assessment": False,
                "is_greeting": True
            }), 200

        if not symptoms:
            return jsonify({
                'possible_conditions': "Please describe your symptoms.",
                'care_recommendation': "Consider seeing a doctor soon.",
                'confidence': None,
                'is_assessment': False,
                'is_question': True,
                'requires_upgrade': False
            }), 400

        # Log the incoming request
        current_app.logger.info(f"Analyzing symptom: {symptoms[:50]}...")
        current_app.logger.info(f"Conversation history length: {len(conversation_history)}")
        current_app.logger.info(f"User authenticated: {is_authenticated}, Tier: {user_tier}")

        # Verify API key is available
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            current_app.logger.error("OpenAI API key not found in environment variables")
            return jsonify({
                'error': 'AI service configuration error.',
                'requires_upgrade': False
            }), 500
        
        # Log partial API key for debugging (first 4 chars only for security)
        current_app.logger.info(f"Using API key starting with: {api_key[:4]}...")
        
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=api_key)

        # Prepare messages with context preservation
        messages, question_count = prepare_messages_with_context(conversation_history, symptoms, context_notes)

        current_app.logger.info(f"Sending {len(messages)} messages to OpenAI")
        current_app.logger.debug(f"Full messages: {json.dumps(messages)}")

        # Try with exponential backoff for handling rate limits and temporary errors
        for attempt in range(MAX_RETRIES):
            try:
                # Use GPT-4 for better structured output adherence
                response = client.chat.completions.create(
                    model="gpt-4",  # Using GPT-4 for better structured output adherence
                    messages=messages,
                    temperature=0.7,
                    max_tokens=750
                )
                
                ai_response = response.choices[0].message.content
                current_app.logger.info(f"Raw OpenAI response: {ai_response[:200]}...")

                # Process the response using the clean_ai_response function from openai_config
                # Pass the current_user to enforce subscription tier restrictions
                processed_response = clean_ai_response(ai_response, current_user)
                
                # Check if this is a JSON response (assessment)
                is_assessment = processed_response.get("is_assessment", False)
                is_question = processed_response.get("is_question", False)
                
                # Check if this requires an upgrade (from clean_ai_response)
                requires_upgrade = processed_response.get("requires_upgrade", False)
                
                # Get confidence level
                confidence = processed_response.get("confidence", None)
                if is_assessment and "assessment" in processed_response and "conditions" in processed_response["assessment"]:
                    conditions = processed_response["assessment"]["conditions"]
                    if conditions and len(conditions) > 0:
                        confidence = conditions[0].get("confidence", 80)
                elif is_assessment:
                    if "multiple possible conditions" in ai_response.lower():
                        confidence = 75
                    elif "strong indication" in ai_response.lower():
                        confidence = 85
                    elif "clear, definitive" in ai_response.lower():
                        confidence = 90
                    else:
                        confidence = 80  # Default confidence for assessments
                
                # ✅ Override requires_upgrade if confidence is too low
                is_confident = confidence is not None and confidence >= MIN_CONFIDENCE_THRESHOLD
                if requires_upgrade and not is_confident:
                    requires_upgrade = False
                    current_app.logger.info(f"Overriding requires_upgrade to False due to low confidence ({confidence})")
                
                # ✅ NEW: Ensure we always have a follow-up question for low confidence
                if is_assessment and not is_confident:
                    # Generate a follow-up question for low confidence assessments
                    follow_up_questions = [
                        "I need more details to be certain. Can you describe when the pain started?",
                        "To better understand your condition, can you tell me if anything makes the symptoms better or worse?",
                        "I'd like to get a clearer picture. Have you noticed any other symptoms along with this?",
                        "To help narrow down the possibilities, can you describe the exact location and nature of your discomfort?",
                        "I need a bit more information. Have you tried any treatments or medications for this issue?"
                    ]
                    # Pick a question that hasn't been asked yet, or use the first one as fallback
                    follow_up_question = follow_up_questions[0]
                    for question in follow_up_questions:
                        if question not in [msg.get("message", "") for msg in conversation_history if msg.get("isBot", False)]:
                            follow_up_question = question
                            break
                    
                    # Override the response to be a question instead of an assessment
                    is_assessment = False
                    is_question = True
                    ai_response = follow_up_question
                    current_app.logger.info(f"Generated follow-up question for low confidence: {follow_up_question}")
                
                current_app.logger.info(f"Final requires_upgrade={requires_upgrade}, confidence={confidence}, is_confident={is_confident}")
                
                # Determine care recommendation
                care_recommendation = "Consider seeing a doctor soon."
                if is_assessment and "assessment" in processed_response:
                    triage_level = processed_response["assessment"].get("triage_level", "MODERATE")
                    if triage_level == "SEVERE":
                        care_recommendation = "You should seek urgent care."
                    elif triage_level == "MILD":
                        care_recommendation = "You can likely manage this at home."
                    else:
                        care_recommendation = processed_response["assessment"].get("care_recommendation", care_recommendation)
                elif any(word in ai_response.lower() for word in ['emergency', 'immediate', 'urgent', 'severe', '911']):
                    care_recommendation = "You should seek urgent care."
                elif all(word in ai_response.lower() for word in ['mild', 'minor', 'normal', 'common']):
                    care_recommendation = "You can likely manage this at home."

                # For one-time report purchases, generate a comprehensive doctor's report
                if one_time_report or (current_user and current_user.subscription_tier == UserTierEnum.ONE_TIME):
                    # Generate a more formal, detailed doctor's report
                    doctor_report_messages = messages.copy()
                    doctor_report_messages.append({
                        "role": "system",
                        "content": """Generate a comprehensive medical summary in a format suitable for healthcare providers. 
                        Include: 
                        1. Patient's reported symptoms with timeline
                        2. Potential diagnoses with confidence levels
                        3. Recommended tests or examinations
                        4. Suggested treatment approaches
                        5. Red flags that would warrant immediate attention
                        Format this as a professional medical document."""
                    })
                    
                    # Use exponential backoff for doctor's report generation too
                    for dr_attempt in range(MAX_RETRIES):
                        try:
                            doctor_report_response = client.chat.completions.create(
                                model="gpt-4",  # Using GPT-4 for better structured output adherence
                                messages=doctor_report_messages,
                                temperature=0.5,
                                max_tokens=1000
                            )
                            
                            doctor_report = doctor_report_response.choices[0].message.content
                            break
                        except (openai.RateLimitError, openai.APIConnectionError, openai.APIError) as e:
                            if dr_attempt == MAX_RETRIES - 1:
                                raise
                            backoff_time = (2 ** dr_attempt) * RETRY_DELAY
                            current_app.logger.info(f"Doctor report generation backing off for {backoff_time} seconds")
                            time.sleep(backoff_time)
                    
                    # Include the doctor's report in the response
                    ai_response = {
                        "standard_response": ai_response,
                        "doctors_report": doctor_report
                    }

                # Save the interaction to the database only for authenticated users
                if is_authenticated and user_id:
                    save_symptom_interaction(user_id, symptoms, ai_response, care_recommendation, confidence, is_assessment)

                # Prepare the response
                if isinstance(ai_response, dict):
                    result = ai_response  # For doctor's report format
                    result['care_recommendation'] = care_recommendation
                    result['confidence'] = confidence
                    result['is_assessment'] = is_assessment
                    result['is_question'] = is_question
                else:
                    # Use the processed response
                    if is_assessment:
                        result = processed_response
                        result['care_recommendation'] = care_recommendation
                        result['confidence'] = confidence
                    else:
                        result = {
                            'possible_conditions': ai_response,
                            'care_recommendation': care_recommendation if is_assessment else None,
                            'confidence': confidence if is_assessment else None,
                            'is_assessment': is_assessment,
                            'is_question': is_question,
                            'triage_level': processed_response.get("assessment", {}).get("triage_level", None) if is_assessment else None
                        }
                
                # Add the requires_upgrade flag from the processed response
                if requires_upgrade:
                    result['requires_upgrade'] = True
                    result['upgrade_options'] = [
                        {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"},
                        {"type": "one_time", "name": "Doctor's Report", "price": 4.99}
                    ]
                else:
                    # Explicitly set requires_upgrade to False to override any previous setting
                    result['requires_upgrade'] = False
                
                # Ensure we always have a question field for the frontend
                if is_question and 'question' not in result:
                    result['question'] = ai_response
                
                return jsonify(result)
                
            except openai.RateLimitError as e:
                current_app.logger.error(f"OpenAI rate limit exceeded (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return jsonify({
                        'error': 'AI service is temporarily busy. Please try again later.',
                        'requires_upgrade': False  # Ensure we don't trigger upgrade on error
                    }), 429
                # Exponential backoff: 2^attempt * RETRY_DELAY seconds (2, 4, 8...)
                backoff_time = (2 ** attempt) * RETRY_DELAY
                current_app.logger.info(f"Backing off for {backoff_time} seconds")
                time.sleep(backoff_time)

            except openai.APIConnectionError as e:
                current_app.logger.error(f"OpenAI API connection error (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return jsonify({
                        'error': 'Unable to connect to AI service. Please try again later.',
                        'requires_upgrade': False  # Ensure we don't trigger upgrade on error
                    }), 503
                backoff_time = (2 ** attempt) * RETRY_DELAY
                time.sleep(backoff_time)

            except openai.APIError as e:
                current_app.logger.error(f"OpenAI API error (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return jsonify({
                        'error': 'AI service error. Please try again later.',
                        'requires_upgrade': False  # Ensure we don't trigger upgrade on error
                    }), 500
                backoff_time = (2 ** attempt) * RETRY_DELAY
                time.sleep(backoff_time)

            except openai.AuthenticationError as e:
                current_app.logger.error(f"OpenAI authentication error: {e}")
                return jsonify({
                    'error': 'AI service authentication error. Please check your API key.',
                    'requires_upgrade': False  # Ensure we don't trigger upgrade on error
                }), 500

            except openai.InvalidRequestError as e:
                current_app.logger.error(f"OpenAI invalid request error: {e}")
                return jsonify({
                    'error': 'Invalid request to AI service.',
                    'requires_upgrade': False  # Ensure we don't trigger upgrade on error
                }), 400
                
            except Exception as e:
                current_app.logger.error(f"Unexpected error (attempt {attempt + 1}): {e}", exc_info=True)
                if attempt == MAX_RETRIES - 1:
                    return jsonify({
                        'error': 'Unable to process your request.',
                        'requires_upgrade': False  # Ensure we don't trigger upgrade on error
                    }), 500
                backoff_time = (2 ** attempt) * RETRY_DELAY
                time.sleep(backoff_time)

    except Exception as e:
        current_app.logger.error(f'Error analyzing symptoms: {e}', exc_info=True)
        return jsonify({
            'error': "I'm having trouble connecting to my medical database. Please check your internet connection and try again.",
            'possible_conditions': "I apologize, but I'm having trouble processing your request right now. Please try again or seek medical attention if you're concerned about your symptoms.",
            'care_recommendation': "Consider seeing a doctor soon.",
            'confidence': None,
            'requires_upgrade': False,  # Explicitly set to False to avoid upgrade prompts on errors
            'is_question': False
        }), 500

def extract_mini_win(ai_response):
    """Extract a small, valuable insight from the full response to show value before upgrade prompt."""
    # Look for the first sentence that mentions a condition or symptom pattern
    sentences = ai_response.split('.')
    
    for sentence in sentences[:3]:  # Check first few sentences
        if any(term in sentence.lower() for term in ['condition', 'symptom', 'suggest', 'indicate', 'pattern', 'likely']):
            return sentence.strip() + "."
    
    # Fallback if no good sentence found
    return "Based on your symptoms, I've identified some initial patterns that could be significant."

def save_symptom_interaction(user_id, symptom_text, ai_response, care_recommendation, confidence, is_assessment):
    """Save the symptom interaction to the database"""
    try:
        # Convert complex response types to JSON string if needed
        if isinstance(ai_response, dict):
            response_text = json.dumps(ai_response)
        else:
            response_text = ai_response
            
        # Create a new symptom record
        new_symptom = Symptom(
            user_id=user_id,
            description=symptom_text,
            response=response_text,
            created_at=datetime.utcnow()
        )
        db.session.add(new_symptom)
        db.session.commit()
        
        # If this is an assessment, create a report
        if is_assessment:
            # Create a report for this assessment
            report_content = {
                "assessment": ai_response if not isinstance(ai_response, dict) else ai_response.get('standard_response', ''),
                "care_recommendation": care_recommendation,
                "confidence": confidence,
                "doctors_report": ai_response.get('doctors_report', '') if isinstance(ai_response, dict) else None
            }
            
            new_report = Report(
                user_id=user_id,
                symptom_id=new_symptom.id,
                content=json.dumps(report_content),
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

@symptom_routes.route('/history', methods=['GET'])
def get_symptom_history():
    """Get symptom history for authenticated users (PA Mode feature)."""
    # Check for JWT token
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
    except Exception as e:
        current_app.logger.warning(f"Authentication required for symptom history: {str(e)}")
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        # Get the user's symptom history
        symptoms = Symptom.query.filter_by(user_id=user_id).order_by(Symptom.created_at.desc()).all()
        
        result = []
        for symptom in symptoms:
            try:
                # Try to parse as JSON first
                try:
                    response_data = json.loads(symptom.response)
                    is_json = True
                except:
                    response_data = symptom.response
                    is_json = False
                
                # Get associated report if it exists
                report = Report.query.filter_by(symptom_id=symptom.id).first()
                
                entry = {
                    'id': symptom.id,
                    'description': symptom.description,
                    'created_at': symptom.created_at.isoformat(),
                    'response': response_data
                }
                
                if report:
                    try:
                        report_content = json.loads(report.content)
                        entry['report'] = report_content
                    except:
                        entry['report'] = {'content': report.content}
                
                result.append(entry)
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
        current_app.logger.error(f"Error retrieving symptom history: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@symptom_routes.route('/doctor-report', methods=['POST'])
def generate_doctor_report():
    """Generate a one-time doctor's report for a specific symptom conversation."""
    data = request.get_json()
    symptoms = data.get('symptom', '')
    conversation_history = data.get('conversation_history', [])
    
    # Check for JWT token to determine if user is authenticated
    auth_header = request.headers.get('Authorization')
    is_authenticated = False
    user_id = None
    
    if auth_header and auth_header.startswith('Bearer '):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            is_authenticated = user_id is not None
        except Exception as e:
            current_app.logger.warning(f"Invalid token provided: {str(e)}")
    
    try:
        # Verify API key is available
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            current_app.logger.error("OpenAI API key not found in environment variables")
            return jsonify({'error': 'AI service configuration error.'}), 500
        
        # Log partial API key for debugging (first 4 chars only for security)
        current_app.logger.info(f"Using API key starting with: {api_key[:4]}...")
        
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=api_key)
        
        # Prepare messages with context preservation for doctor's report
        messages, _ = prepare_messages_with_context(conversation_history, symptoms)
        
        # Replace the system message with doctor's report specific instructions
        messages[0] = {
            "role": "system",
            "content": """Generate a comprehensive medical summary in a format suitable for healthcare providers. 
            Include: 
            1. Patient's reported symptoms with timeline
            2. Potential diagnoses with confidence levels
            3. Recommended tests or examinations
            4. Suggested treatment approaches
            5. Red flags that would warrant immediate attention
            Format this as a professional medical document."""
        }
        
        # Try with exponential backoff for handling rate limits and temporary errors
        for attempt in range(MAX_RETRIES):
            try:
                response = client.chat.completions.create(
                    model="gpt-4",  # Using GPT-4 for better structured output adherence
                    messages=messages,
                    temperature=0.5,
                    max_tokens=1000
                )
                
                doctor_report = response.choices[0].message.content
                
                # Determine care recommendation for the report
                care_recommendation = "Consider seeing a doctor soon."
                if any(word in doctor_report.lower() for word in ['emergency', 'immediate', 'urgent', 'severe', '911']):
                    care_recommendation = "You should seek urgent care."
                elif all(word in doctor_report.lower() for word in ['mild', 'minor', 'normal', 'common']):
                    care_recommendation = "You can likely manage this at home."
                
                # Save to database if authenticated
                if is_authenticated and user_id:
                    # Create a report record
                    report_content = {
                        "doctors_report": doctor_report,
                        "care_recommendation": care_recommendation,
                        "generated_at": datetime.utcnow().isoformat(),
                        "one_time_purchase": True
                    }
                    
                    # Find or create a symptom record
                    symptom = Symptom.query.filter_by(
                        user_id=user_id, 
                        description=symptoms
                    ).order_by(Symptom.created_at.desc()).first()
                    
                    if not symptom:
                        symptom = Symptom(
                            user_id=user_id,
                            description=symptoms,
                            response="One-time doctor's report generated",
                            created_at=datetime.utcnow()
                        )
                        db.session.add(symptom)
                        db.session.commit()
                    
                    new_report = Report(
                        user_id=user_id,
                        symptom_id=symptom.id,
                        content=json.dumps(report_content),
                        created_at=datetime.utcnow()
                    )
                    db.session.add(new_report)
                    db.session.commit()
                
                return jsonify({
                    "doctors_report": doctor_report,
                    "care_recommendation": care_recommendation,
                    "success": True
                })
                
            except openai.RateLimitError as e:
                current_app.logger.error(f"OpenAI rate limit exceeded (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return jsonify({'error': 'AI service is temporarily busy. Please try again later.'}), 429
                # Exponential backoff: 2^attempt * RETRY_DELAY seconds (2, 4, 8...)
                backoff_time = (2 ** attempt) * RETRY_DELAY
                current_app.logger.info(f"Backing off for {backoff_time} seconds")
                time.sleep(backoff_time)

            except openai.APIConnectionError as e:
                current_app.logger.error(f"OpenAI API connection error (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return jsonify({'error': 'Unable to connect to AI service. Please try again later.'}), 503
                backoff_time = (2 ** attempt) * RETRY_DELAY
                time.sleep(backoff_time)

            except openai.APIError as e:
                current_app.logger.error(f"OpenAI API error (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return jsonify({'error': 'AI service error. Please try again later.'}), 500
                backoff_time = (2 ** attempt) * RETRY_DELAY
                time.sleep(backoff_time)

            except openai.AuthenticationError as e:
                current_app.logger.error(f"OpenAI authentication error: {e}")
                return jsonify({'error': 'AI service authentication error. Please check your API key.'}), 500

            except openai.InvalidRequestError as e:
                current_app.logger.error(f"OpenAI invalid request error: {e}")
                return jsonify({'error': 'Invalid request to AI service.'}), 400
                
            except Exception as e:
                current_app.logger.error(f"Unexpected error (attempt {attempt + 1}): {e}", exc_info=True)
                if attempt == MAX_RETRIES - 1:
                    return jsonify({'error': 'Unable to process your request.'}), 500
                backoff_time = (2 ** attempt) * RETRY_DELAY
                time.sleep(backoff_time)
                
    except Exception as e:
        current_app.logger.error(f"Error generating doctor's report: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Failed to generate doctor's report",
            "success": False
        }), 500