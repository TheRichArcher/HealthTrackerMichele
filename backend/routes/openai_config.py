import re
import json
import logging
from typing import Dict, List, Union
from flask import current_app
from backend.config import Config  # Ensures API key handling aligns with config.py

# Set up logging with detailed format
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constants for confidence levels and response formatting
MIN_CONFIDENCE = 10  # Allowing lower confidence for nuanced assessments
MAX_CONFIDENCE = 95  # Preventing overconfidence
DEFAULT_CONFIDENCE = 75

SYSTEM_PROMPT = """You are Michele, an AI medical assistant trained to have conversations like a doctor's visit.
Your goal is to understand the user's symptoms through a conversation before providing any potential diagnosis.

CONVERSATION FLOW:
1. Begin by asking about symptoms if the user hasn't provided them.
2. ALWAYS ask follow-up questions about the symptoms ONE AT A TIME. Never combine multiple questions in a single message.
3. After gathering sufficient information (at least 2-3 follow-up questions), provide a structured diagnosis.

STANDARD FOLLOW-UP SEQUENCE:
1. **Duration** – "How long have you had this symptom?"
2. **Severity** – "On a scale of 1-10, how bad is it?"
3. **Triggers** – "Does anything make it better or worse?"
4. **Additional Symptoms** – "Have you noticed anything else?"

CRITICAL RULES:
1. NEVER ask more than one question in a single message.
2. If you need multiple pieces of information, ask for them in separate, sequential messages.
3. Wait for the user to respond to each question before asking the next one.
4. CAREFULLY review the conversation history before asking questions to avoid redundancy.

CONTEXT AWARENESS RULES:
1. PAY CLOSE ATTENTION to timing information the user has already provided (e.g., "woke up with", "started yesterday").
2. If the user mentions they "woke up with" a symptom, this means it started that morning - DO NOT ask how long they've had it.
3. NEVER ask about symptoms the user has already described.
4. TRACK all symptoms mentioned throughout the conversation, even if mentioned casually.

FINAL ASSESSMENT FORMAT:
The AI must return JSON structured like this:
- "conditions": A list of conditions with names, confidence levels, and explanations.
- "care_recommendation": One of MILD, MODERATE, or SEVERE.
- "reasoning": A brief explanation of the assessment.

NEVER provide an assessment before asking at least 2-3 follow-up questions.
"""


def create_default_response() -> Dict:
    """
    Provides a default structured response when AI fails to process input.
    """
    return {
        "is_assessment": True,
        "is_question": False,
        "assessment": {
            "conditions": [
                {"name": "Unable to analyze symptoms", "confidence": DEFAULT_CONFIDENCE, "description": "Insufficient data provided."}
            ],
            "care_recommendation": "MODERATE",
            "reasoning": "Consider consulting a healthcare professional if symptoms persist.",
            "disclaimer": "This assessment is for informational purposes only and does not replace professional medical advice."
        }
    }


def calculate_confidence(conditions_list: List[Dict]) -> List[Dict]:
    """
    Dynamically adjusts confidence levels based on AI response structure and content.
    """
    total_conditions = len(conditions_list)
    base_confidence = 90 if total_conditions == 1 else (80 if total_conditions == 2 else 65)

    for condition in conditions_list:
        name_lower = condition.get("name", "").lower()
        description_lower = condition.get("description", "").lower()
        combined_text = name_lower + " " + description_lower

        # Adjust confidence based on language used
        if "clear, definitive" in combined_text or "very likely" in combined_text:
            condition["confidence"] = min(base_confidence + 10, MAX_CONFIDENCE)
        elif "most likely" in combined_text:
            condition["confidence"] = min(base_confidence + 5, MAX_CONFIDENCE)
        elif "likely" in combined_text:
            condition["confidence"] = base_confidence
        elif "suggests" in combined_text:
            condition["confidence"] = max(base_confidence - 10, MIN_CONFIDENCE + 10)
        elif "could be" in combined_text:
            condition["confidence"] = max(base_confidence - 15, MIN_CONFIDENCE + 10)
        elif "possibly" in combined_text:
            condition["confidence"] = max(base_confidence - 20, MIN_CONFIDENCE + 10)
        elif "might be" in combined_text:
            condition["confidence"] = max(base_confidence - 25, MIN_CONFIDENCE + 5)
        elif "uncertain" in combined_text or "unclear" in combined_text:
            condition["confidence"] = max(base_confidence - 30, MIN_CONFIDENCE + 5)
        elif "unlikely" in combined_text:
            condition["confidence"] = MIN_CONFIDENCE + 5
        else:
            condition["confidence"] = base_confidence

        # Ensure confidence is within bounds
        condition["confidence"] = min(MAX_CONFIDENCE, max(MIN_CONFIDENCE, condition["confidence"]))

    return conditions_list


def clean_ai_response(response_text: str) -> Union[Dict, str]:
    """
    Processes the AI response and determines if it's a question or assessment.
    """
    if not isinstance(response_text, str) or not response_text.strip():
        logger.warning("Invalid or empty response")
        return create_default_response()
    
    logger.info(f"Processing AI response: {response_text[:100]}...")
    
    json_match = re.search(r'```json\s*(.*?)\s*```|({[\s\S]*"assessment"[\s\S]*})', response_text, re.DOTALL)
    
    if json_match:
        try:
            json_str = json_match.group(1) or json_match.group(2)
            json_str = json_str.strip()
            assessment_data = json.loads(json_str)
            assessment_data["is_assessment"] = True
            assessment_data["is_question"] = False
            
            if "assessment" in assessment_data and "conditions" in assessment_data["assessment"]:
                assessment_data["assessment"]["conditions"] = calculate_confidence(assessment_data["assessment"]["conditions"])
            
            return assessment_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
    
    return {"is_assessment": False, "is_question": "?" in response_text, "question": response_text.strip()}
