import json
import logging
from typing import Dict, Optional
from flask import current_app
from backend.models import User, UserTierEnum  # Explicitly import User

# Configure logging
logger = logging.getLogger(__name__)

# Constants
MIN_CONFIDENCE_THRESHOLD = 90  # Synced with Chat.jsx and symptom_routes.py

# System prompt for OpenAI
SYSTEM_PROMPT = """You are Michele, an AI medical assistant designed to mimic a doctor's visit. Your goal is to understand the user's symptoms through conversation and provide insights only when highly confident.

CRITICAL INSTRUCTIONS:
1. ALWAYS return a valid JSON response with these exact fields:
   - "is_assessment": boolean (true only if confidence ≥ 90% for a diagnosis)
   - "is_question": boolean (true if asking a follow-up question)
   - "possible_conditions": string (question text if is_question, condition name/description if is_assessment)
   - "confidence": number (0-100, null if no assessment)
   - "triage_level": string ("MILD", "MODERATE", "SEVERE", null if no assessment)
   - "care_recommendation": string (brief advice, null if no assessment)
   - "requires_upgrade": boolean (set by backend, default false)
   Optional:
   - "assessment": object (if is_assessment=true, with "conditions", "triage_level", "care_recommendation")
   - "doctors_report": string (if requested)

2. For assessments (is_assessment=true):
   - Include an "assessment" object: {"conditions": [{"name": "Medical Term (Common Name)", "confidence": number}], "triage_level": string, "care_recommendation": string}
   - Only provide an assessment if confidence is ≥ 90%.
   - Use 'Medical Term (Common Name)' format (e.g., "Rhinitis (Common Cold)").

3. Conversation flow:
   - For the first user message, set "is_question": true and ask a follow-up question.
   - Ask clear, single questions until you reach ≥ 90% confidence or gather enough context.
   - Avoid diagnosing unless confidence meets the threshold.
   - For potentially serious conditions (e.g., stroke, heart attack), ask differentiating questions until certain.
   - For common conditions (e.g., common cold, sunburn), suggest home care if appropriate.

4. Be concise, empathetic, and precise. Avoid guessing—ask questions if unsure.
5. Include "doctors_report" as a formatted string only when explicitly requested.
"""

def clean_ai_response(
    response_text: str,
    user: Optional[User] = None,  # Use User directly now that it's imported
    conversation_history: Optional[list] = None,
    symptom: str = ""
) -> Dict:
    """
    Process OpenAI API response, ensuring valid JSON output.

    Args:
        response_text: Raw response string from OpenAI.
        user: User object (optional) for tier-based logic.
        conversation_history: List of prior messages (optional).
        symptom: Current symptom input (optional).

    Returns:
        Dict: Processed JSON response adhering to SYSTEM_PROMPT structure.
    """
    # Log input details
    is_production = current_app.config.get("ENV") == "production"
    logger.setLevel(logging.INFO if is_production else logging.DEBUG)
    logger.debug(f"Processing symptom: {symptom}")
    if conversation_history:
        logger.debug(f"Conversation history: {json.dumps(conversation_history)}")
    logger.info(f"Raw AI response: {response_text[:100]}...")

    # Handle empty or invalid response
    if not isinstance(response_text, str) or not response_text.strip():
        logger.warning("Empty or invalid AI response received")
        return {
            "is_assessment": False,
            "is_question": True,
            "possible_conditions": "I couldn’t process that—can you describe your symptoms again?",
            "confidence": None,
            "triage_level": None,
            "care_recommendation": None,
            "requires_upgrade": False,
            "disclaimer": "This is for informational purposes only, not a substitute for medical advice."
        }

    try:
        # Parse JSON response
        parsed_json = json.loads(response_text)
        if not isinstance(parsed_json, dict):
            raise ValueError("Response is not a dictionary")

        # Define required fields with defaults
        required_fields = {
            "is_assessment": False,
            "is_question": True,
            "possible_conditions": "Can you tell me more about your symptoms?",
            "confidence": None,
            "triage_level": None,
            "care_recommendation": None,
            "requires_upgrade": False
        }

        # Ensure all required fields are present
        for field, default in required_fields.items():
            parsed_json.setdefault(field, default)
            if parsed_json[field] is None and field not in ["confidence", "triage_level", "care_recommendation"]:
                logger.warning(f"Field '{field}' is None, setting to default")
                parsed_json[field] = default

        # Enforce mutual exclusivity of is_assessment and is_question
        if parsed_json["is_assessment"] and parsed_json["is_question"]:
            logger.warning("Both is_assessment and is_question are true, prioritizing question")
            parsed_json["is_assessment"] = False
            parsed_json["is_question"] = True

        # Validate assessment confidence
        if parsed_json["is_assessment"]:
            confidence = parsed_json.get("confidence")
            if confidence is None or confidence < MIN_CONFIDENCE_THRESHOLD:
                logger.info(f"Confidence {confidence} below {MIN_CONFIDENCE_THRESHOLD}%, converting to question")
                parsed_json["is_assessment"] = False
                parsed_json["is_question"] = True
                parsed_json["possible_conditions"] = "I need more details to be certain—can you describe any other symptoms?"
                parsed_json["confidence"] = None
                parsed_json["triage_level"] = None
                parsed_json["care_recommendation"] = None
                if "assessment" in parsed_json:
                    del parsed_json["assessment"]

        # Log processed response
        logger.info(f"Processed response: {json.dumps(parsed_json, indent=2)}")
        return parsed_json

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse response as JSON: {str(e)}")
        # Fallback to text-based parsing
        is_question = "?" in response_text
        return {
            "is_assessment": False,
            "is_question": is_question,
            "possible_conditions": response_text.strip() if is_question else "Can you tell me more about your symptoms?",
            "confidence": None,
            "triage_level": None,
            "care_recommendation": None,
            "requires_upgrade": False
        }
    except Exception as e:
        logger.error(f"Unexpected error processing response: {str(e)}", exc_info=True)
        return {
            "is_assessment": False,
            "is_question": True,
            "possible_conditions": "Something went wrong—can you try again?",
            "confidence": None,
            "triage_level": None,
            "care_recommendation": None,
            "requires_upgrade": False
        }