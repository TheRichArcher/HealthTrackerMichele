import openai
import os
import json
import logging
import random
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2
MIN_CONFIDENCE_THRESHOLD = 95
MAX_TOKENS = 1500
TEMPERATURE = 0.7
MIN_USER_RESPONSES_FOR_ASSESSMENT = 3

# Set up logging
logger = logging.getLogger(__name__)

# System prompt for OpenAI
SYSTEM_PROMPT = """
You are Michele, an AI medical assistant designed to help users understand their symptoms and provide health insights. Your role is to:

- Ask clarifying questions to gather more information about symptoms.
- Provide possible medical conditions based on the symptoms described.
- Include a confidence level (0-100%) for each assessment.
- List other less likely conditions with their confidence levels under "other_conditions".
- Suggest a triage level (LOW, MODERATE, HIGH, EMERGENCY) and care recommendation.
- Respond in JSON format with the following structure:
  {
    "is_assessment": boolean,
    "is_question": boolean,
    "possible_conditions": string,
    "confidence": number|null,
    "triage_level": string|null,
    "care_recommendation": string|null,
    "requires_upgrade": boolean,
    "assessment": {
      "conditions": [{"name": string, "confidence": number}]
    },
    "other_conditions": [{"name": string, "confidence": number}]
  }

- If the confidence is below 95%, set "is_assessment" to false and "is_question" to true, and provide a follow-up question in "possible_conditions".
- If the user has not provided enough information (fewer than 3 user responses), set "is_question" to true and provide a follow-up question in "possible_conditions".
- When "is_question" is true, "possible_conditions" MUST contain a follow-up question as a string (e.g., "When did these symptoms first start?"). Do NOT set "possible_conditions" to null.
- For critical symptoms (e.g., chest pain, shortness of breath), ask specific follow-up questions.
- Do not provide a definitive diagnosis; always recommend consulting a healthcare provider for serious conditions.
"""

# Initialize OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set")

@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=RETRY_DELAY, max=10),
    retry=retry_if_exception_type((openai.RateLimitError, openai.APIError))
)
def call_openai_api(messages, response_format=None, max_tokens=MAX_TOKENS):
    """
    Call the OpenAI API with retry logic for rate limits and API errors.
    
    Args:
        messages (list): List of message dictionaries for the OpenAI API.
        response_format (dict, optional): Response format specification.
        max_tokens (int): Maximum tokens for the response.
    
    Returns:
        str: The content of the OpenAI response.
    """
    logger.info("Calling OpenAI API")
    try:
        client = openai.OpenAI(api_key=openai.api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *messages
            ],
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
            response_format=response_format
        )
        content = response.choices[0].message.content
        logger.info(f"OpenAI API response: {content}")
        return content
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {str(e)}", exc_info=True)
        raise

def build_openai_messages(conversation_history, symptom):
    """
    Build the message list for OpenAI API calls.
    
    Args:
        conversation_history (list): List of conversation entries.
        symptom (str): The latest symptom input from the user.
    
    Returns:
        list: List of message dictionaries.
    """
    messages = []
    for entry in conversation_history:
        role = "assistant" if entry.get("isBot", False) else "user"
        messages.append({"role": role, "content": entry.get("message", "")})
    if not conversation_history or conversation_history[-1].get("isBot", False):
        messages.append({"role": "user", "content": symptom})
    return messages

def clean_ai_response(raw_response, user, conversation_history, symptom):
    """Clean and validate OpenAI API response without overriding question content."""
    # Log input details for debugging
    logger.debug(f"Processing symptom: {symptom}")
    if conversation_history:
        logger.debug(f"Conversation history: {json.dumps(conversation_history)}")
    logger.info(f"Raw AI response: {raw_response[:100]}...")

    # Handle empty or invalid response
    if not isinstance(raw_response, str) or not raw_response.strip():
        logger.warning("Empty or invalid AI response received")
        return {
            "is_assessment": False,
            "is_question": True,
            "possible_conditions": "I couldn’t process that—can you describe your symptoms again?",
            "confidence": None,
            "triage_level": None,
            "care_recommendation": None,
            "requires_upgrade": getattr(user, "subscription_tier", "FREE") not in ["PAID", "ONE_TIME"],
            "assessment": {"conditions": []},
            "other_conditions": [],
            "disclaimer": "This is for informational purposes only, not a substitute for medical advice."
        }

    try:
        # Parse JSON response
        parsed_json = json.loads(raw_response)
        if not isinstance(parsed_json, dict):
            raise ValueError("Response is not a dictionary")

        # Ensure all required fields are present with defaults
        defaults = {
            "is_assessment": False,
            "is_question": True,
            "possible_conditions": "Can you tell me more about your symptoms?",
            "confidence": None,
            "triage_level": None,
            "care_recommendation": None,
            "requires_upgrade": getattr(user, "subscription_tier", "FREE") not in ["PAID", "ONE_TIME"],
            "assessment": {"conditions": []},
            "other_conditions": []
        }
        for key, value in defaults.items():
            parsed_json.setdefault(key, value)
            if parsed_json[key] is None and key not in ["confidence", "triage_level", "care_recommendation"]:
                logger.warning(f"Field '{key}' is None, setting to default")
                parsed_json[key] = value

        # Enforce mutual exclusivity of is_assessment and is_question
        if parsed_json["is_assessment"] and parsed_json["is_question"]:
            logger.warning("Both is_assessment and is_question are true, prioritizing question")
            parsed_json["is_assessment"] = False
            parsed_json["is_question"] = True

        # Validate confidence for assessments
        if parsed_json["is_assessment"]:
            confidence = parsed_json.get("confidence")
            if confidence is None or confidence < MIN_CONFIDENCE_THRESHOLD:
                logger.info(f"Confidence {confidence} below {MIN_CONFIDENCE_THRESHOLD}%, converting to question")
                parsed_json["is_assessment"] = False
                parsed_json["is_question"] = True
                # Preserve OpenAI’s question; fallback only if invalid
                if not parsed_json["possible_conditions"] or "?" not in parsed_json["possible_conditions"]:
                    parsed_json["possible_conditions"] = "I need more information to be confident—can you provide more details?"
                parsed_json["confidence"] = None
                parsed_json["triage_level"] = None
                parsed_json["care_recommendation"] = None
                parsed_json["assessment"] = {"conditions": []}

        # Ensure only one question at a time when is_question is true
        if parsed_json["is_question"]:
            question_text = parsed_json["possible_conditions"]
            # Check for multiple questions (more than one '?' or conjunctions like 'and'/'or' with questions)
            if question_text.count("?") > 1 or (" and " in question_text.lower() and "?" in question_text):
                logger.warning(f"Multiple questions detected in possible_conditions: {question_text}")
                # Extract the first question using regex to find up to the first '?'
                first_question_match = re.search(r"[^.?!]*\?", question_text)
                if first_question_match:
                    parsed_json["possible_conditions"] = first_question_match.group(0).strip()
                    logger.info(f"Trimmed to first question: {parsed_json['possible_conditions']}")
                else:
                    parsed_json["possible_conditions"] = "Can you tell me more about your symptoms?"
                    logger.info("No clear first question found, using default")

        # Ensure possible_conditions is never empty or null
        if not parsed_json["possible_conditions"]:
            logger.warning("possible_conditions empty – returning error fallback")
            parsed_json["possible_conditions"] = "I'm not sure what to ask—can you rephrase or try again?"
            parsed_json["is_question"] = True

        # Validate assessment structure for downstream use (e.g., PDF generation)
        if parsed_json["is_assessment"]:
            if "assessment" not in parsed_json or not isinstance(parsed_json["assessment"], dict):
                logger.warning("Assessment field missing or invalid, converting to question")
                parsed_json["is_assessment"] = False
                parsed_json["is_question"] = True
                parsed_json["possible_conditions"] = parsed_json["possible_conditions"] or "I couldn’t identify a condition—can you provide more details?"
                parsed_json["confidence"] = None
                parsed_json["triage_level"] = None
                parsed_json["care_recommendation"] = None
                parsed_json["assessment"] = {"conditions": []}
            elif "conditions" not in parsed_json["assessment"] or not isinstance(parsed_json["assessment"]["conditions"], list):
                logger.warning("Assessment conditions missing or invalid, converting to question")
                parsed_json["is_assessment"] = False
                parsed_json["is_question"] = True
                parsed_json["possible_conditions"] = parsed_json["possible_conditions"] or "I couldn’t identify a condition—can you provide more details?"
                parsed_json["confidence"] = None
                parsed_json["triage_level"] = None
                parsed_json["care_recommendation"] = None
                parsed_json["assessment"] = {"conditions": []}
            elif not parsed_json["assessment"]["conditions"]:
                logger.warning("Assessment conditions list is empty, converting to question")
                parsed_json["is_assessment"] = False
                parsed_json["is_question"] = True
                parsed_json["possible_conditions"] = parsed_json["possible_conditions"] or "I couldn’t identify a condition—can you provide more details?"
                parsed_json["confidence"] = None
                parsed_json["triage_level"] = None
                parsed_json["care_recommendation"] = None
                parsed_json["assessment"] = {"conditions": []}
            else:
                # Ensure conditions are properly formatted for downstream parsing
                for condition in parsed_json["assessment"]["conditions"]:
                    if "name" not in condition or not isinstance(condition["name"], str):
                        logger.warning(f"Invalid condition name: {condition}, setting to default")
                        condition["name"] = "Unknown (N/A)"
                    if "confidence" not in condition or not isinstance(condition["confidence"], (int, float)):
                        logger.warning(f"Invalid condition confidence: {condition}, setting to 0")
                        condition["confidence"] = 0

        # Validate triage_level and care_recommendation for assessments
        if parsed_json["is_assessment"]:
            valid_triage_levels = ["LOW", "MODERATE", "HIGH", "EMERGENCY"]
            if parsed_json.get("triage_level") not in valid_triage_levels:
                logger.warning(f"Invalid triage_level '{parsed_json.get('triage_level')}', defaulting to MODERATE")
                parsed_json["triage_level"] = "MODERATE"
            if not parsed_json["care_recommendation"]:
                logger.info("care_recommendation missing for assessment, setting default")
                parsed_json["care_recommendation"] = "Consult a healthcare provider."

        # Ensure other_conditions is a list
        if "other_conditions" not in parsed_json or not isinstance(parsed_json["other_conditions"], list):
            logger.warning(f"other_conditions invalid or missing: {parsed_json.get('other_conditions')}, setting to empty list")
            parsed_json["other_conditions"] = []

        logger.info(f"Processed response: {json.dumps(parsed_json, indent=2)}")
        return parsed_json

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse response as JSON: {str(e)}")
        return {
            "is_assessment": False,
            "is_question": True,
            "possible_conditions": "I couldn’t process that—can you describe your symptoms again?",
            "confidence": None,
            "triage_level": None,
            "care_recommendation": None,
            "requires_upgrade": getattr(user, "subscription_tier", "FREE") not in ["PAID", "ONE_TIME"],
            "assessment": {"conditions": []},
            "other_conditions": []
        }
    except Exception as e:
        logger.error(f"Unexpected error processing response: {str(e)}", exc_info=True)
        return {
            "is_assessment": False,
            "is_question": True,
            "possible_conditions": "I encountered an issue processing your information. Could you try describing your symptoms again?",
            "confidence": None,
            "triage_level": None,
            "care_recommendation": None,
            "requires_upgrade": getattr(user, "subscription_tier", "FREE") not in ["PAID", "ONE_TIME"],
            "assessment": {"conditions": []},
            "other_conditions": []
        }