import openai
import os
import json
import logging
import random
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
    """
    Clean and validate the OpenAI API response.
    
    Args:
        raw_response (str): Raw response from OpenAI API.
        user (User): The user object (or MockUser for unauthenticated users).
        conversation_history (list): List of conversation entries.
        symptom (str): The latest symptom input from the user.
    
    Returns:
        dict: Cleaned and validated response dictionary.
    """
    try:
        parsed_json = json.loads(raw_response)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response as JSON: {raw_response}, error: {str(e)}")
        return {
            "is_assessment": False,
            "is_question": True,
            "possible_conditions": "I'm sorry, I couldn't process that. Can you describe your symptoms again?",
            "confidence": None,
            "triage_level": None,
            "care_recommendation": None,
            "requires_upgrade": False,
            "other_conditions": []
        }

    # Validate required fields
    required_fields = ["is_assessment", "is_question", "possible_conditions"]
    for field in required_fields:
        if field not in parsed_json:
            logger.warning(f"Missing required field '{field}' in OpenAI response: {parsed_json}")
            parsed_json[field] = False if field in ["is_assessment", "is_question"] else ""

    # Fix missing or null possible_conditions in all cases
    if not parsed_json.get("possible_conditions"):
        logger.warning("possible_conditions is empty or null after cleaning, setting default question")
        parsed_json["possible_conditions"] = random.choice([
            "Can you describe your symptoms in more detail?",
            "When did these symptoms start?",
            "Is anything making it better or worse?",
            "Have you experienced this before?",
            "Are you taking any medications or have any health conditions?"
        ])

    # Count user responses in conversation history
    user_response_count = sum(1 for entry in conversation_history if not entry.get("isBot", False))
    if user_response_count < MIN_USER_RESPONSES_FOR_ASSESSMENT and parsed_json.get("is_assessment", False):
        logger.info(f"User has only {user_response_count} responses, need {MIN_USER_RESPONSES_FOR_ASSESSMENT} for assessment")
        parsed_json["is_assessment"] = False
        parsed_json["is_question"] = True
        parsed_json["possible_conditions"] = "I need more information to make an assessment. Can you tell me more about your symptoms?"
        parsed_json["confidence"] = None
        parsed_json["triage_level"] = None
        parsed_json["care_recommendation"] = None
        parsed_json["assessment"] = {"conditions": []}
        parsed_json["other_conditions"] = []

    # Check for critical symptoms that require specific questions
    combined_text = symptom.lower() + " " + " ".join(
        entry.get("message", "").lower() for entry in conversation_history
    )
    critical_symptoms = ["chest pain", "shortness of breath", "severe headache", "sudden numbness", "severe abdominal pain"]
    has_critical_symptoms = any(symptom in combined_text for symptom in critical_symptoms)

    if not parsed_json.get("is_assessment", False) and not parsed_json.get("is_question", False):
        parsed_json["is_question"] = True
        if has_critical_symptoms:
            if "chest pain" in combined_text or "shortness of breath" in combined_text:
                parsed_json["possible_conditions"] = "Does the chest discomfort get worse with exertion, like walking or climbing stairs?"
            elif "severe headache" in combined_text:
                parsed_json["possible_conditions"] = "Is the headache sudden and severe, or did it come on gradually?"
            elif "sudden numbness" in combined_text:
                parsed_json["possible_conditions"] = "Is the numbness on one side of your body, and did it start suddenly?"
            elif "severe abdominal pain" in combined_text:
                parsed_json["possible_conditions"] = "Is the pain localized to one area, or does it spread? Any nausea or vomiting?"
        else:
            varied_questions = [
                "When did these symptoms first start?",
                "Have you noticed anything that makes the symptoms better or worse?",
                "Are you experiencing any other symptoms, like fever, fatigue, or nausea?",
                "Have you had these symptoms before, or is this the first time?",
                "Are you taking any medications or do you have any known medical conditions?"
            ]
            parsed_json["possible_conditions"] = random.choice(varied_questions)

    # Ensure other_conditions is present
    if "other_conditions" not in parsed_json:
        parsed_json["other_conditions"] = []

    # Validate confidence for assessments
    if parsed_json["is_assessment"]:
        confidence = parsed_json.get("confidence")
        if confidence is None or confidence < MIN_CONFIDENCE_THRESHOLD:
            logger.info(f"Confidence {confidence} below {MIN_CONFIDENCE_THRESHOLD}%, converting to question")
            parsed_json["is_assessment"] = False
            parsed_json["is_question"] = True
            parsed_json["possible_conditions"] = "I need more details to make a confident assessment. Can you tell me more about your symptoms?"
            parsed_json["confidence"] = None
            parsed_json["triage_level"] = None
            parsed_json["care_recommendation"] = None
            parsed_json["assessment"] = {"conditions": []}
            parsed_json["other_conditions"] = []

    # Ensure assessment field is present and properly formatted
    if parsed_json.get("is_assessment", False):
        if "assessment" not in parsed_json or not isinstance(parsed_json["assessment"], dict):
            parsed_json["assessment"] = {"conditions": []}
        if "conditions" not in parsed_json["assessment"] or not isinstance(parsed_json["assessment"]["conditions"], list):
            parsed_json["assessment"]["conditions"] = []
        if not parsed_json["assessment"]["conditions"]:
            logger.warning("Assessment conditions list is empty, converting to question")
            parsed_json["is_assessment"] = False
            parsed_json["is_question"] = True
            parsed_json["possible_conditions"] = "I couldn't identify a condition with the given information. Can you provide more details?"
            parsed_json["confidence"] = None
            parsed_json["triage_level"] = None
            parsed_json["care_recommendation"] = None
            parsed_json["assessment"] = {"conditions": []}
            parsed_json["other_conditions"] = []

    # Validate triage_level and care_recommendation
    if parsed_json.get("is_assessment", False):
        valid_triage_levels = ["LOW", "MODERATE", "HIGH", "EMERGENCY"]
        if parsed_json.get("triage_level") not in valid_triage_levels:
            parsed_json["triage_level"] = "MODERATE"
        if not parsed_json.get("care_recommendation"):
            parsed_json["care_recommendation"] = "Consult a healthcare provider for a definitive diagnosis."

    # Set requires_upgrade based on user tier
    subscription_tier = getattr(user, "subscription_tier", "FREE")
    parsed_json["requires_upgrade"] = subscription_tier not in ["PAID", "ONE_TIME"]

    return parsed_json