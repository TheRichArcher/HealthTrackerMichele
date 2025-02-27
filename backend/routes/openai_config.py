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
2. ALWAYS ask 2-3 follow-up questions before considering a diagnosis.
   - Tailor questions based on the symptom provided.
   - Do NOT ask the same set of questions for every symptom.
3. Once enough information is gathered, provide a structured response.

FOLLOW-UP QUESTIONING LOGIC:
- **Headache:** "Do you have nausea or sensitivity to light?"
- **Cough:** "Is the cough dry or producing mucus?"
- **Fever:** "Do you have chills or body aches?"
- **Injury:** "Is there swelling or bleeding?"

IMPORTANT RULES:
1. NEVER ask a question the user has already answered.
2. DO NOT start questions by repeating the user’s response.
3. Accept single-character inputs where applicable (e.g., severity rating from 1-10).
4. If a symptom description is vague, ask for clarification instead of assuming.

FINAL ASSESSMENT FORMAT:
The AI must return JSON structured like this:
```json
{
  "assessment": {
    "conditions": [
      {"name": "Condition 1", "confidence": 70},
      {"name": "Condition 2", "confidence": 20},
      {"name": "Condition 3", "confidence": 10}
    ],
    "triage_level": "MILD|MODERATE|SEVERE",
    "care_recommendation": "Brief recommendation based on triage level",
    "disclaimer": "This assessment is for informational purposes only and does not replace professional medical advice."
  }
}
```
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
            return assessment_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
    
    # Prevent repeating already-answered questions
    asked_questions = set()
    for phrase in ["woke up with", "suddenly started", "since this morning"]:
        if phrase in response_text.lower():
            asked_questions.add("How long have you had this symptom?")
    
    # Remove redundant questions from response
    for question in asked_questions:
        response_text = response_text.replace(question, "")
    
    # Handle single-character inputs
    if response_text.strip().isdigit():
        return {"is_assessment": False, "is_question": False, "answer": int(response_text.strip())}
    
    return {"is_assessment": False, "is_question": "?" in response_text, "question": response_text.strip()}
