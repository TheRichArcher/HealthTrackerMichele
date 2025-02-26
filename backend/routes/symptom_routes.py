from flask import Blueprint, request, jsonify, current_app
from backend.routes.extensions import db
from backend.models import User, Symptom, Report
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
import openai
import os
import json
import logging
import time
from datetime import datetime

# Blueprint setup
symptom_routes = Blueprint('symptom_routes', __name__)

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2

class UserTier:
    FREE = "free"  # Nurse Mode
    PAID = "paid"  # PA Mode
    ONE_TIME = "one_time"  # Doctor's Report

@symptom_routes.route('/analyze', methods=['POST'])
def analyze_symptoms():
    """Public endpoint for symptom analysis with tiered access."""
    # Check for JWT token to determine if user is authenticated and their tier
    auth_header = request.headers.get('Authorization')
    is_authenticated = False
    user_id = None
    user_tier = UserTier.FREE  # Default to free tier (Nurse Mode)
    
    if auth_header and auth_header.startswith('Bearer '):
        try:
            # Optional JWT verification - if token exists and is valid, we'll save the history
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            is_authenticated = user_id is not None
            
            # In a real implementation, you would fetch the user's subscription tier from the database
            if is_authenticated:
                user = User.query.get(user_id)
                user_tier = getattr(user, 'subscription_tier', UserTier.PAID)  # Use default if attribute doesn't exist
        except Exception as e:
            current_app.logger.warning(f"Invalid token provided: {str(e)}")
            # Continue as unauthenticated user
    
    try:
        data = request.get_json()
        symptoms = data.get('symptom', '')
        conversation_history = data.get('conversation_history', [])
        one_time_report = data.get('one_time_report', False)  # Flag for one-time Doctor's Report purchase

        if not symptoms:
            return jsonify({
                'possible_conditions': "Please describe your symptoms.",
                'care_recommendation': "Consider seeing a doctor soon.",
                'confidence': None
            }), 400

        # Log the incoming request
        current_app.logger.info(f"Analyzing symptom: {symptoms[:50]}...")
        current_app.logger.info(f"Conversation history length: {len(conversation_history)}")
        current_app.logger.info(f"User authenticated: {is_authenticated}, Tier: {user_tier}")

        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        if not client.api_key:
            current_app.logger.error("OpenAI API key not found")
            raise ValueError("OpenAI API key not configured")

        messages = [
            {
                "role": "system",
                "content": """You are HealthTracker AI, an advanced medical screening assistant with three modes:

1. NURSE MODE (Free Tier): Provides basic assessment for mild conditions only.
2. PA MODE (Paid Tier): Provides comprehensive assessment for all conditions.
3. DOCTOR'S REPORT (One-Time Purchase): Provides detailed medical summary.

STRICT QUESTION FLOW:
1. **First, check ALL previous messages AND current message for timing information.**
   - If timing was mentioned ANYWHERE (e.g., "this morning", "2 days ago", "since yesterday"), **skip to step 2.**
   - If no timing found in ANY message, ask: "How long have you been experiencing these symptoms?"
   - Wait for response.

2. **Check for severity information.**
   - If they mentioned severity or intensity, skip to step 3.
   - If not mentioned, ask: "On a scale of 1-10, how severe are your symptoms?"
   - Wait for response.

3. **Ask ONE targeted follow-up based on symptoms:**
   - **For pain:** "Does the pain respond to anti-inflammatory medication?"
   - **For fever:** "Have you noticed any patterns in when the fever appears?"
   - **For shortness of breath:** "Do you experience any wheezing or chest tightness?"
   - **For dizziness:** "Have you noticed if certain positions or movements trigger it?"
   - Wait for response.

4. **Only after three responses, provide an assessment**:
   - **Primary Condition (Confidence Level)**:
     * 90-95%: Clear, definitive symptoms with minimal alternatives.
     * 75-85%: Strong indication but other possibilities exist.
     * 60-74%: Multiple possible conditions.

   - **Alternative Possibilities**:
     1. Condition (XX% confidence) - Why this is less likely.
     2. Condition (XX% confidence) - Why this is less likely.

5. **Care Recommendation**:
   - **"You can likely manage this at home."**: Stable symptoms, no major concerns.
   - **"Consider seeing a doctor soon."**: Significant discomfort, affecting daily life.
   - **"You should seek urgent care."**: Emergency signs present.

🚨 **Emergency Protocol**:
- If user mentions "chest pain," "difficulty breathing," or "confusion":
  - Skip question sequence and **immediately** recommend emergency care.

CRITICAL RULES:
- Never ask more than ONE question per response.
- Do NOT repeat questions if the user already answered them.
- Diagnosis **only after** three structured questions.
- Include a disclaimer that this does NOT replace medical advice."""
            }
        ]

        # Add conversation history
        for entry in conversation_history:
            role = "assistant" if entry.get("isBot", False) else "user"
            content = entry.get("message", "")
            current_app.logger.debug(f"Adding message to history - Role: {role}, Content: {content[:50]}...")
            messages.append({"role": role, "content": content})

        # Add the current symptom if not already in conversation
        if not conversation_history or conversation_history[-1].get("isBot", False):
            messages.append({"role": "user", "content": symptoms})

        current_app.logger.info(f"Sending {len(messages)} messages to OpenAI")

        # Try with retries for handling rate limits and temporary errors
        for attempt in range(MAX_RETRIES):
            try:
                response = client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=750
                )
                
                ai_response = response.choices[0].message.content
                current_app.logger.info(f"Raw OpenAI response: {ai_response[:200]}...")

                # Determine if this is a question or an assessment
                is_assessment = False
                if "Primary Condition" in ai_response or "Care Recommendation" in ai_response:
                    is_assessment = True

                # Determine care recommendation
                care_recommendation = "Consider seeing a doctor soon."
                if any(word in ai_response.lower() for word in ['emergency', 'immediate', 'urgent', 'severe', '911']):
                    care_recommendation = "You should seek urgent care."
                elif all(word in ai_response.lower() for word in ['mild', 'minor', 'normal', 'common']):
                    care_recommendation = "You can likely manage this at home."

                # Determine confidence score
                confidence = None  # Default to None before assessment
                if "Primary Condition" in ai_response:
                    if "multiple possible conditions" in ai_response.lower():
                        confidence = 75
                    elif "strong indication" in ai_response.lower():
                        confidence = 85
                    elif "clear, definitive" in ai_response.lower():
                        confidence = 90

                # Apply tier-based limitations
                requires_upgrade = False
                upgrade_options = []
                
                # For free users (Nurse Mode) with non-mild conditions, limit information
                if is_assessment and user_tier == UserTier.FREE and care_recommendation != "You can likely manage this at home.":
                    # Extract a "mini-win" insight to show value before upgrade prompt
                    mini_win = extract_mini_win(ai_response)
                    
                    # For moderate or severe conditions, limit information for free tier
                    ai_response = f"""{mini_win}

Based on your symptoms, I'm seeing a pattern that suggests this may require more detailed analysis.

Care Recommendation: {care_recommendation}

To unlock deeper insights into your symptoms, you have two options:

1. Upgrade to PA Mode ($9.99/month) for:
   - Comprehensive assessment of all conditions
   - Ongoing symptom tracking
   - Personalized health insights
   - Unlimited consultations

2. Purchase a one-time Doctor's Report ($4.99) for:
   - Detailed analysis of this specific case
   - Formatted summary you can share with healthcare providers
   - Specific recommendations for next steps

Disclaimer: This assessment is for informational purposes only and does not replace professional medical advice."""
                    
                    # Set requires_upgrade flag and options
                    requires_upgrade = True
                    upgrade_options = [
                        {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"},
                        {"type": "one_time", "name": "Doctor's Report", "price": 4.99}
                    ]
                
                # For one-time report purchases, generate a comprehensive doctor's report
                elif one_time_report or user_tier == UserTier.ONE_TIME:
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
                    
                    doctor_report_response = client.chat.completions.create(
                        model="gpt-4-turbo-preview",
                        messages=doctor_report_messages,
                        temperature=0.5,
                        max_tokens=1000
                    )
                    
                    doctor_report = doctor_report_response.choices[0].message.content
                    
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
                else:
                    result = {
                        'possible_conditions': ai_response,
                        'care_recommendation': care_recommendation,
                        'confidence': confidence,
                        'is_assessment': is_assessment
                    }
                
                if requires_upgrade:
                    result['requires_upgrade'] = True
                    result['upgrade_options'] = upgrade_options
                
                return jsonify(result)
                
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

    except Exception as e:
        current_app.logger.error(f'Error analyzing symptoms: {e}')
        return jsonify({
            'possible_conditions': "I apologize, but I'm having trouble processing your request right now. Please try again or seek medical attention if you're concerned about your symptoms.",
            'care_recommendation': "Consider seeing a doctor soon.",
            'confidence': None
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
        current_app.logger.error(f"Error retrieving symptom history: {str(e)}")
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
        # This would be where you'd implement payment processing
        # For now, we'll just generate the report
        
        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        messages = [
            {
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
        ]
        
        # Add conversation history
        for entry in conversation_history:
            role = "assistant" if entry.get("isBot", False) else "user"
            content = entry.get("message", "")
            messages.append({"role": role, "content": content})
        
        # Add the current symptom if not already in conversation
        if not conversation_history or conversation_history[-1].get("isBot", False):
            messages.append({"role": "user", "content": symptoms})
        
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
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
        
    except Exception as e:
        current_app.logger.error(f"Error generating doctor's report: {str(e)}")
        return jsonify({
            "error": "Failed to generate doctor's report",
            "success": False
        }), 500