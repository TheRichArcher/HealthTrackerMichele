from flask import Blueprint, request, jsonify, current_app
from backend.routes.extensions import db
from backend.models import User, Symptom, Report, UserTierEnum
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
import openai
import os
import json
import logging
import time
from datetime import datetime

# Blueprint setup
symptom_routes = Blueprint("symptom_routes", __name__)

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_FREE_MESSAGES = 15
MIN_CONFIDENCE_THRESHOLD = 90  # Aligned with frontend threshold
JSON_RETRY_ATTEMPTS = 2  # Number of attempts to get valid JSON before falling back

# Set OpenAI API key globally
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set")

# Define MockUser class once
class MockUser:
    subscription_tier = "free"  # Use string instead of Enum reference

# Define is_premium_user at the top before using it
def is_premium_user(user):
    """Check if the user has premium access."""
    return getattr(user, "subscription_tier", "free") in {"paid", "one_time"}

def process_with_openai(symptom, conversation_history, current_user, options=None):
    """
    Process symptom analysis with OpenAI API
    
    Args:
        symptom: Current symptom text
        conversation_history: List of conversation messages
        current_user: User object with subscription tier
        options: Dict with additional options (one_time_report, context_notes)
    
    Returns:
        Dict with processed response
    """
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    is_production = current_app.config.get("ENV") == "production" if current_app else False
    
    # Get options
    options = options or {}
    one_time_report = options.get("one_time_report", False)
    context_notes = options.get("context_notes", "")
    
    # Determine user tier and premium status
    is_premium = is_premium_user(current_user)
    user_tier = getattr(current_user, "subscription_tier", "free")
    
    # Count questions asked so far
    question_count = sum(1 for msg in conversation_history if msg.get("isBot", False) and "?" in msg.get("message", ""))
    
    # Extract all user symptoms for context
    user_messages = [msg.get("message", "") for msg in conversation_history if not msg.get("isBot", False)]
    symptom_context = "; ".join(user_messages) if user_messages else symptom
    
    # Build the system prompt with all necessary instructions
    system_prompt = f"""You are Michele, an AI medical assistant trained to analyze symptoms and provide medical insights.

CONVERSATION CONTEXT:
User has reported: {symptom_context}
Questions asked so far: {question_count}
User subscription tier: {user_tier}
One-time report requested: {one_time_report}
Additional context: {context_notes}

CRITICAL INSTRUCTIONS:
1. ALWAYS return a JSON response with the following structure:
{{
  "is_assessment": boolean,  // True if providing a diagnosis with ≥{MIN_CONFIDENCE_THRESHOLD}% confidence
  "is_question": boolean,    // True if asking a follow-up question
  "possible_conditions": string,  // Main response text (question or assessment)
  "confidence": number,      // Confidence level (0-100)
  "triage_level": string,    // "MILD", "MODERATE", or "SEVERE"
  "care_recommendation": string,  // Brief care advice
  "requires_upgrade": boolean,  // True if detailed insights require premium access
  "assessment": {{           // Only include if is_assessment is true
    "conditions": [
      {{
        "name": string,      // Medical term (Common name)
        "confidence": number,
        "is_chronic": boolean
      }}
    ],
    "triage_level": string,
    "care_recommendation": string
  }},
  "doctors_report": string   // Only include if one_time_report is true and user is premium
}}

2. DIAGNOSIS REQUIREMENTS:
   - Ask at least 5 follow-up questions before considering a diagnosis
   - NEVER provide a diagnosis if confidence is <{MIN_CONFIDENCE_THRESHOLD}%
   - If you cannot reach {MIN_CONFIDENCE_THRESHOLD}% confidence, ask another follow-up question instead
   - Always include both medical term and common name for conditions: "Medical Term (Common Name)"
   - For potentially serious conditions, ask more questions to properly differentiate

3. TIER-SPECIFIC BEHAVIOR:
   - For FREE tier users:
     - DO provide specific condition names (not generic "Digestive Issue")
     - DO provide basic triage level (mild/moderate/severe)
     - DO NOT provide detailed treatment plans or comprehensive explanations
     - Set requires_upgrade=true for high-confidence assessments
     - Include a teaser like "For more detailed insights, consider upgrading"
   
   - For PAID or ONE_TIME tier users:
     - Provide full details, treatment suggestions, and comprehensive explanations
     - Set requires_upgrade=false
     - Include doctors_report if one_time_report is true

4. TRIAGE GUIDELINES:
   - MILD: Conditions manageable at home (e.g., common cold, sunburn)
   - MODERATE: Conditions benefiting from medical consultation but not urgent
   - SEVERE: Conditions requiring immediate medical attention

5. SPECIAL CASES:
   - For common mild conditions like sunburn, always set triage_level="MILD"
   - For stroke vs. migraine, ask about symptom onset (sudden vs. gradual)
   - For chronic conditions (IBS, GERD, migraines), verify recurring pattern
   - For uncertain answers, ask more specific, direct questions

6. RESPONSE FORMAT:
   - For questions: Conversational, single question format
   - For assessments: Clear, concise explanation with confidence level
   - Never combine multiple questions in one response
"""

    # Prepare conversation history for OpenAI
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history
    for entry in conversation_history:
        role = "assistant" if entry.get("isBot", False) else "user"
        content = entry.get("message", "")
        messages.append({"role": role, "content": content})
    
    # Add current symptom if not already in conversation
    if not conversation_history or conversation_history[-1].get("isBot", False):
        messages.append({"role": "user", "content": symptom})
    
    # Try with exponential backoff for handling rate limits and temporary errors
    for attempt in range(MAX_RETRIES):
        try:
            if not is_production and symptom:
                logger.debug(f"Processing symptom request: {symptom[:50]}")
                logger.debug(f"OpenAI messages: {json.dumps(messages)}")
            
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=1500
            )
            
            # Handle empty or invalid response
            if not response.choices or not response.choices[0].message or "content" not in response.choices[0].message or not response.choices[0].message["content"].strip():
                logger.error("OpenAI returned an empty or malformed response")
                return {"error": "AI service did not return a valid response. Please try again later.", "requires_upgrade": False}

            response_text = response.choices[0].message["content"]
            
            if not is_production:
                logger.info(f"Raw OpenAI response: {response_text}")
            
            # Parse JSON response with retry for invalid JSON
            json_retry_count = 0
            while json_retry_count < JSON_RETRY_ATTEMPTS:
                try:
                    result = json.loads(response_text)
                    
                    # Validate the result has required fields
                    required_fields = {"is_assessment", "is_question", "possible_conditions", "confidence", "triage_level", "care_recommendation"}
                    missing_fields = required_fields - result.keys()
                    
                    if missing_fields:
                        if json_retry_count < JSON_RETRY_ATTEMPTS - 1:
                            retry_message = (
                                "Your response is missing required fields or is not valid JSON. "
                                "Ensure your reply follows the required JSON format and includes: "
                                "'is_assessment', 'is_question', 'possible_conditions', 'confidence', 'triage_level', 'care_recommendation'. "
                                "Please try again."
                            )
                            messages.append({"role": "user", "content": retry_message})
                            
                            if not is_production:
                                logger.warning(f"Missing fields in JSON response: {missing_fields}. Retrying.")
                            
                            response = openai.chat.completions.create(
                                model="gpt-4",
                                messages=messages,
                                response_format={"type": "json_object"},
                                temperature=0.7,
                                max_tokens=1500
                            )
                            
                            if not response.choices or not response.choices[0].message or "content" not in response.choices[0].message or not response.choices[0].message["content"].strip():
                                logger.error("OpenAI returned an empty response on retry")
                                return {"error": "AI response was empty on retry", "requires_upgrade": False}
                            
                            response_text = response.choices[0].message["content"]
                            if not is_production:
                                logger.info(f"Retry raw OpenAI response: {response_text}")
                            
                            json_retry_count += 1
                            continue
                    
                    # Check confidence level for assessments and force follow-up question if too low
                    if result.get("is_assessment", False):
                        confidence = result.get("confidence", 0)
                        if confidence < MIN_CONFIDENCE_THRESHOLD:
                            if json_retry_count < JSON_RETRY_ATTEMPTS - 1:
                                retry_message = (
                                    "Your response is missing required fields or is not valid JSON. "
                                    "Ensure your reply follows the required JSON format and includes: "
                                    "'is_assessment', 'is_question', 'possible_conditions', 'confidence', 'triage_level', 'care_recommendation'. "
                                    "Please try again."
                                )
                                messages.append({"role": "user", "content": retry_message})
                                
                                if not is_production:
                                    logger.warning(f"Confidence too low: {confidence}%. Requesting follow-up question instead.")
                                
                                response = openai.chat.completions.create(
                                    model="gpt-4",
                                    messages=messages,
                                    response_format={"type": "json_object"},
                                    temperature=0.7,
                                    max_tokens=1500
                                )
                                
                                if not response.choices or not response.choices[0].message or "content" not in response.choices[0].message or not response.choices[0].message["content"].strip():
                                    logger.error("OpenAI returned an empty response on retry")
                                    return {"error": "AI response was empty on retry", "requires_upgrade": False}
                                
                                response_text = response.choices[0].message["content"]
                                if not is_production:
                                    logger.info(f"Retry raw OpenAI response: {response_text}")
                                
                                json_retry_count += 1
                                continue
                    
                    # Ensure all required fields are present with defaults
                    default_response = {
                        "is_assessment": False,
                        "is_question": False,
                        "possible_conditions": "",
                        "confidence": None,
                        "triage_level": None,
                        "care_recommendation": None,
                        "requires_upgrade": False,
                    }
                    result = {**default_response, **result}
                    
                    # For free users, enforce upgrade requirements for assessments
                    if not is_premium and result.get("is_assessment", False):
                        confidence = result.get("confidence", 0)
                        triage_level = result.get("triage_level", "")
                        
                        # Check if this is a common mild condition
                        condition_name = ""
                        if "assessment" in result and "conditions" in result["assessment"]:
                            if result["assessment"]["conditions"] and len(result["assessment"]["conditions"]) > 0:
                                condition_name = result["assessment"]["conditions"][0].get("name", "").lower()
                        
                        is_common_mild = any(term in condition_name.lower() for term in [
                            "common cold", "seasonal allergy", "mild headache", "tension headache",
                            "sinus infection", "sinusitis", "sunburn", "acid reflux"
                        ])
                        
                        # Set requires_upgrade based on confidence and condition type
                        if (not is_premium) and confidence >= MIN_CONFIDENCE_THRESHOLD and not is_common_mild and triage_level and triage_level.upper() not in {"MILD"}:
                            result["requires_upgrade"] = True
                        else:
                            result["requires_upgrade"] = False
                    else:
                        # Premium users never require upgrade
                        result["requires_upgrade"] = False
                    
                    # Log the final processed result in debug mode
                    if not is_production:
                        logger.debug(f"Final processed result: {json.dumps(result)}")
                    
                    return result
                    
                except json.JSONDecodeError as e:
                    if json_retry_count < JSON_RETRY_ATTEMPTS - 1:
                        retry_message = (
                            "Your response is missing required fields or is not valid JSON. "
                            "Ensure your reply follows the required JSON format and includes: "
                            "'is_assessment', 'is_question', 'possible_conditions', 'confidence', 'triage_level', 'care_recommendation'. "
                            "Please try again."
                        )
                        messages.append({"role": "user", "content": retry_message})
                        
                        if not is_production:
                            logger.warning(f"Invalid JSON response: {e}. Retrying.")
                        
                        response = openai.chat.completions.create(
                            model="gpt-4",
                            messages=messages,
                            response_format={"type": "json_object"},
                            temperature=0.7,
                            max_tokens=1500
                        )
                        
                        if not response.choices or not response.choices[0].message or "content" not in response.choices[0].message or not response.choices[0].message["content"].strip():
                            logger.error("OpenAI returned an empty response on retry")
                            return {"error": "AI response was empty on retry", "requires_upgrade": False}
                        
                        response_text = response.choices[0].message["content"]
                        if not is_production:
                            logger.info(f"Retry raw OpenAI response: {response_text}")
                        
                        json_retry_count += 1
                    else:
                        logger.error(f"Failed to get valid JSON after {JSON_RETRY_ATTEMPTS} attempts: {e}")
                        return {"error": "Invalid AI response format after multiple attempts", "requires_upgrade": False}
                
        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error (Attempt {attempt + 1}): {str(e)}", exc_info=True)
            
            # Specific handling for rate limits
            if "Rate limit" in str(e) and attempt < MAX_RETRIES - 1:
                wait_time = (2 ** attempt) * RETRY_DELAY
                logger.warning(f"Rate limit hit. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue

            if attempt == MAX_RETRIES - 1:
                return {"error": "AI service is temporarily unavailable. Please try again later.", "requires_upgrade": False}
            
        except Exception as e:
            logger.error(f"Unexpected error (Attempt {attempt + 1}): {e}", exc_info=True)
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep((2 ** attempt) * RETRY_DELAY)
    
    # If we get here, all attempts failed
    raise RuntimeError("Failed to get response from OpenAI after multiple attempts")

@symptom_routes.route("/debug", methods=["GET"])
def debug_route():
    """Debug endpoint to check subscription enforcement logic"""
    logger = logging.getLogger(__name__)
    user_id = None
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
    except Exception:
        pass  # Handle as anonymous user
    current_user = User.query.get(user_id) if user_id else MockUser()
    logger.info(f"Debug endpoint called for user {user_id if user_id else 'Anonymous'}")
    
    logger.info(f"Created mock user with tier: {getattr(current_user, 'subscription_tier', 'Unknown')}")
    
    # Test response
    test_symptom = "My eye is red, itchy, and has a crusty discharge"
    test_history = [
        {"isBot": False, "message": test_symptom},
        {"isBot": True, "message": "How long have you been experiencing these symptoms?"},
        {"isBot": False, "message": "About 2 days now"}
    ]
    
    # Process with OpenAI
    try:
        result = process_with_openai(test_symptom, test_history, current_user, {})
        logger.info(f"Debug result for user {user_id if user_id else 'Anonymous'}: {result}")
        
        return jsonify({
            "symptom": test_symptom,
            "processed_result": result,
            "requires_upgrade": result.get("requires_upgrade", False),
            "user_tier": getattr(current_user, "subscription_tier", "free")
        }), 200
    except Exception as e:
        logger.error(f"Debug error for user {user_id if user_id else 'Anonymous'}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@symptom_routes.route("/reset", methods=["POST"])
def reset_conversation():
    """Reset the conversation history"""
    user_id = None
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
    except Exception:
        pass  # Handle as anonymous user
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info(f"Reset conversation requested by user {user_id if user_id else 'Anonymous'}")
    current_user = User.query.get(user_id) if user_id else MockUser()
    data = request.get_json() or {}
    conversation_history = data.get("conversation_history", [])

    if (not is_premium_user(current_user)) and sum(1 for msg in conversation_history if not msg.get("isBot", False)) >= MAX_FREE_MESSAGES:
        return jsonify({
            "message": "Free users cannot reset conversation after reaching the limit. Please upgrade to continue.",
            "requires_upgrade": True,
            "upgrade_options": [
                {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"},
                {"type": "one_time", "name": "Doctor's Report", "price": 4.99}
            ]
        }), 403

    return jsonify({
        "message": "Conversation reset successfully",
        "possible_conditions": "Hello! I'm your AI medical assistant. Please describe your symptoms.",
        "is_assessment": False,
        "is_greeting": True
    }), 200

@symptom_routes.route("/analyze", methods=["POST"])
def analyze_symptoms():
    """Public endpoint for symptom analysis with tiered access"""
    is_production = current_app.config.get("ENV") == "production"
    logger = current_app.logger
    
    auth_header = request.headers.get("Authorization")
    is_authenticated = False
    user_id = None
    current_user = None
    
    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            is_authenticated = user_id is not None
            if is_authenticated:
                current_user = User.query.get(user_id)
                if current_user and not is_production:
                    logger.info(f"User {user_id if user_id else 'Anonymous'} subscription tier: {getattr(current_user, 'subscription_tier', 'Unknown')}")
        except Exception as e:
            logger.warning(f"Invalid token provided by user {user_id if user_id else 'Anonymous'}: {str(e)}")
    
    if not current_user:
        current_user = MockUser()
        if not is_authenticated and not is_production:
            logger.info("Handling unauthenticated user as a free-tier user.")
    
    try:
        data = request.get_json() or {}
        symptoms = data.get("symptom", "")
        conversation_history = data.get("conversation_history", [])
        context_notes = data.get("context_notes", "")
        one_time_report = data.get("one_time_report", False)
        reset = data.get("reset", False)
        
        if not is_production and symptoms:
            logger.debug(f"Processing symptom request: {symptoms[:50]}")
        
        if reset:
            if (not is_premium_user(current_user)) and sum(1 for msg in conversation_history if not msg.get("isBot", False)) >= MAX_FREE_MESSAGES:
                return jsonify({
                    "message": "Free users cannot reset conversation after reaching the limit. Please upgrade to continue.",
                    "requires_upgrade": True,
                    "upgrade_options": [
                        {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"},
                        {"type": "one_time", "name": "Doctor's Report", "price": 4.99}
                    ]
                }), 403

            return jsonify({
                "message": "Conversation reset successfully",
                "possible_conditions": "Hello! I'm your AI medical assistant. Please describe your symptoms.",
                "is_assessment": False,
                "is_greeting": True
            }), 200
        
        if not is_premium_user(current_user):
            user_message_count = sum(1 for msg in conversation_history if not msg.get("isBot", False))
            if user_message_count >= MAX_FREE_MESSAGES:
                return jsonify({
                    "message": "You've reached the free message limit. Please upgrade to continue or reset your conversation to start over.",
                    "requires_upgrade": True,
                    "can_reset": True,
                    "upgrade_options": [
                        {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"},
                        {"type": "one_time", "name": "Doctor's Report", "price": 4.99}
                    ]
                }), 200

        if not symptoms:
            return jsonify({
                "possible_conditions": "Please describe your symptoms.",
                "care_recommendation": "Consider seeing a doctor soon.",
                "confidence": None,
                "is_assessment": False,
                "is_question": True,
                "requires_upgrade": False
            }), 400

        if not is_production:
            logger.info(f"Conversation history length for user {user_id if user_id else 'Anonymous'}: {len(conversation_history)}")
            logger.info(f"User authenticated: {is_authenticated}, Premium: {is_premium_user(current_user)}")

        options = {
            "one_time_report": one_time_report,
            "context_notes": context_notes
        }
        
        result = process_with_openai(symptoms, conversation_history, current_user, options)
        
        if is_authenticated and user_id:
            save_symptom_interaction(user_id, symptoms, result, result.get("care_recommendation"), result.get("confidence"), result.get("is_assessment", False))
        
        return jsonify(result)
        
    except openai.OpenAIError as e:
        logger.error(f"OpenAI API error for user {user_id if user_id else 'Anonymous'}: {str(e)}", exc_info=True)
        return jsonify({
            "error": "AI service is temporarily unavailable. Please try again later.",
            "requires_upgrade": False
        }), 503
        
    except openai.AuthenticationError:
        logger.error(f"OpenAI authentication error for user {user_id if user_id else 'Anonymous'}: {str(e)}", exc_info=True)
        return jsonify({
            "error": "AI service authentication error. Please check your API key.",
            "requires_upgrade": False
        }), 500
        
    except openai.InvalidRequestError:
        logger.error(f"OpenAI invalid request error for user {user_id if user_id else 'Anonymous'}: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Invalid request to AI service.",
            "requires_upgrade": False
        }), 400
        
    except Exception as e:
        logger.error(f"Error analyzing symptoms for user {user_id if user_id else 'Anonymous'}: {str(e)}", exc_info=True)
        return jsonify({
            "error": "I'm having trouble connecting to my medical database. Please check your internet connection and try again.",
            "possible_conditions": "I apologize, but I'm having trouble processing your request right now. Please try again or seek medical attention if you're concerned about your symptoms.",
            "care_recommendation": "Consider seeing a doctor soon.",
            "confidence": None,
            "requires_upgrade": False,
            "is_question": False
        }), 500

def save_symptom_interaction(user_id, symptom_text, ai_response, care_recommendation, confidence, is_assessment):
    """Save the symptom interaction to the database"""
    try:
        logger = current_app.logger if current_app else logging.getLogger(__name__)
        if isinstance(ai_response, dict):
            response_text = json.dumps(ai_response)
        else:
            response_text = ai_response
            
        new_symptom = Symptom(
            user_id=user_id,
            description=symptom_text,
            response=response_text,
            created_at=datetime.utcnow()
        )
        db.session.add(new_symptom)
        db.session.commit()
        
        if is_assessment:
            report_content = {
                "assessment": ai_response.get("possible_conditions", ""),
                "care_recommendation": care_recommendation,
                "confidence": confidence,
                "doctors_report": ai_response.get("doctors_report", "")
            }
            
            new_report = Report(
                user_id=user_id,
                symptom_id=new_symptom.id,
                content=json.dumps(report_content),
                created_at=datetime.utcnow()
            )
            db.session.add(new_report)
            db.session.commit()
            
            if current_app.config.get("ENV") != "production":
                logger.info(f"Created report for assessment with ID: {new_report.id} for user {user_id if user_id else 'Anonymous'}")
                
        return True
    except Exception as e:
        logger.error(f"Error saving symptom interaction for user {user_id if user_id else 'Anonymous'}: {str(e)}", exc_info=True)
        if "database" in str(e).lower():
            db.session.rollback()
        return False

@symptom_routes.route("/history", methods=["GET"])
def get_symptom_history():
    """Get symptom history for authenticated users (PA Mode feature)"""
    user_id = None
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
    except Exception as e:
        current_app.logger.warning(f"Authentication required for symptom history by user {user_id if user_id else 'Anonymous'}: {str(e)}")
        return jsonify({"error": "Authentication required"}), 401
    
    current_user = User.query.get(user_id)
    if not current_user or getattr(current_user, "subscription_tier", "free") != "paid":
        return jsonify({
            "error": "Premium subscription required for symptom history", 
            "requires_upgrade": True,
            "upgrade_options": [
                {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"}
            ]
        }), 403
    
    try:
        symptoms = Symptom.query.filter_by(user_id=user_id).order_by(Symptom.created_at.desc()).all()
        result = []
        for symptom in symptoms:
            try:
                try:
                    response_data = json.loads(symptom.response)
                    is_json = True
                except json.JSONDecodeError:
                    response_data = symptom.response
                    is_json = False
                
                report = Report.query.filter_by(symptom_id=symptom.id).first()
                entry = {
                    "id": symptom.id,
                    "description": symptom.description,
                    "created_at": symptom.created_at.isoformat(),
                    "response": response_data
                }
                if report:
                    try:
                        report_content = json.loads(report.content)
                        entry["report"] = report_content
                    except json.JSONDecodeError:
                        entry["report"] = {"content": report.content}
                result.append(entry)
            except Exception as e:
                current_app.logger.error(f"Error processing symptom {symptom.id} for user {user_id if user_id else 'Anonymous'}: {str(e)}")
                result.append({
                    "id": symptom.id,
                    "description": symptom.description,
                    "created_at": symptom.created_at.isoformat(),
                    "error": "Failed to process response"
                })
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error retrieving symptom history for user {user_id if user_id else 'Anonymous'}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@symptom_routes.route("/doctor-report", methods=["POST"])
def generate_doctor_report():
    """Generate a one-time doctor's report for a specific symptom conversation"""
    is_production = current_app.config.get("ENV") == "production"
    logger = current_app.logger
    
    auth_header = request.headers.get("Authorization")
    is_authenticated = False
    user_id = None
    current_user = None
    
    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            is_authenticated = user_id is not None
            if is_authenticated:
                current_user = User.query.get(user_id)
        except Exception as e:
            logger.warning(f"Invalid token provided by user {user_id if user_id else 'Anonymous'}: {str(e)}")
    
    if not current_user or not is_premium_user(current_user):
        return jsonify({
            "error": "You need a PA Mode subscription or a one-time purchase to generate a doctor's report.",
            "requires_upgrade": True,
            "upgrade_options": [
                {"type": "subscription", "name": "PA Mode", "price": 9.99, "period": "month"},
                {"type": "one_time", "name": "Doctor's Report", "price": 4.99}
            ]
        }), 403
    
    data = request.get_json() or {}
    symptoms = data.get("symptom", "")
    conversation_history = data.get("conversation_history", [])
    
    if not is_production and symptoms:
        logger.debug(f"Processing doctor's report request: {symptoms[:50]}")
    
    try:
        if is_authenticated and user_id:
            symptom = Symptom.query.filter_by(user_id=user_id, description=symptoms).order_by(Symptom.created_at.desc()).first()
            if symptom:
                existing_report = Report.query.filter_by(user_id=user_id, symptom_id=symptom.id).first()
                if existing_report:
                    try:
                        report_content = json.loads(existing_report.content)
                        doctor_report = report_content.get("doctors_report", "")
                        if doctor_report:
                            if not is_production:
                                logger.info(f"Using existing doctor's report for user {user_id if user_id else 'Anonymous'}")
                            return jsonify({
                                "doctors_report": doctor_report,
                                "care_recommendation": report_content.get("care_recommendation", "Consider seeing a doctor soon."),
                                "success": True,
                                "from_cache": True
                            })
                    except json.JSONDecodeError:
                        pass
        
        options = {
            "one_time_report": True,
            "context_notes": "Generate a comprehensive medical report suitable for healthcare providers"
        }
        
        result = process_with_openai(symptoms, conversation_history, current_user, options)
        
        doctor_report = result.get("doctors_report", "")
        if not doctor_report:
            doctor_report = f"""
MEDICAL CONSULTATION REPORT
Date: {datetime.utcnow().strftime("%Y-%m-%d")}

PATIENT SYMPTOMS:
{symptoms}

ASSESSMENT:
{result.get("possible_conditions", "Unable to determine specific condition")}

CONFIDENCE LEVEL: {result.get("confidence", "Unknown")}%

CARE RECOMMENDATION:
{result.get("care_recommendation", "Consider consulting with a healthcare provider")}

NOTES:
This report was generated based on the symptoms provided. For a definitive diagnosis, please consult with a healthcare provider.
"""
        
        if is_authenticated and user_id:
            report_content = {
                "doctors_report": doctor_report,
                "care_recommendation": result.get("care_recommendation", "Consider seeing a doctor soon."),
                "generated_at": datetime.utcnow().isoformat(),
                "one_time_purchase": True
            }
            
            symptom = Symptom.query.filter_by(user_id=user_id, description=symptoms).order_by(Symptom.created_at.desc()).first()
            if not symptom:
                symptom = Symptom(
                    user_id=user_id,
                    description=symptoms,
                    response="One-time doctor's report generated",
                    created_at=datetime.utcnow()
                )
                db.session.add(symptom)
                db.session.commit()
            
            existing_report = Report.query.filter_by(user_id=user_id, symptom_id=symptom.id).first()
            if existing_report:
                existing_report.content = json.dumps(report_content)
                existing_report.created_at = datetime.utcnow()
                db.session.commit()
            else:
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
            "care_recommendation": result.get("care_recommendation", "Consider seeing a doctor soon."),
            "success": True
        })
        
    except Exception as e:
        logger.error(f"Error generating doctor's report for user {user_id if user_id else 'Anonymous'}: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Failed to generate doctor's report",
            "success": False
        }), 500