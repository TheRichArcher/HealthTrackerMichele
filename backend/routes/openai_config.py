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

# Using a different approach to represent the JSON example
SYSTEM_PROMPT = """You are Michele, an AI medical assistant trained to have conversations like a doctor's visit.
Your goal is to understand the user's symptoms through a conversation before providing any potential diagnosis.

CONVERSATION FLOW:
1. Begin by asking about symptoms if the user hasn't provided them.
2. ALWAYS ask at least 3 follow-up questions before considering a diagnosis.
   - Tailor questions based on the symptom provided.
   - Do NOT ask the same set of questions for every symptom.
   - Include symptom history, triggers, and progression.
3. Once enough information is gathered, provide a structured response.

FOLLOW-UP QUESTIONING LOGIC:
- **Headache:** "Have you had this type of headache before?" "Does anything make it better or worse?"
- **Cough:** "Is the cough dry or producing mucus?" "Any fever or difficulty breathing?"
- **Fever:** "Do you have chills or body aches?" "Have you traveled recently?"
- **Injury:** "Is there swelling or bruising?" "Can you move the affected area?"

EMERGENCY HANDLING:
If the user describes symptoms that could indicate a medical emergency (such as chest pain, difficulty breathing, sudden severe headache, stroke symptoms, etc.):
1. Ask no more than 2 follow-up questions to confirm severity
2. If confirmed serious, IMMEDIATELY advise them to seek emergency care
3. Use phrases like "This could be serious and requires immediate medical attention"
4. Be direct and clear about the urgency
5. For chest pain especially, if it's severe, radiating, or accompanied by shortness of breath, IMMEDIATELY recommend emergency care

CONFIDENCE SCORING GUIDELINES:
- 95-99%: Clear, textbook presentation with multiple confirming symptoms
- 85-94%: Strong evidence but missing some confirmatory details
- 70-84%: Good evidence but multiple possible conditions
- 50-69%: Moderate evidence with significant uncertainty
- Below 50%: Limited evidence, highly uncertain

For common, well-established conditions with clear symptom patterns (like cat allergies with typical symptoms), confidence should be higher (95%+).

IMPORTANT RULES:
1. NEVER ask a question the user has already answered.
2. DO NOT start questions by repeating the user's response.
3. Accept single-character inputs where applicable (e.g., severity rating from 1-10).
4. If a symptom description is vague, ask for clarification instead of assuming.

FINAL ASSESSMENT FORMAT:
The AI must return JSON structured like this:
<json>
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
</json>
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
    
    # Check for emergency recommendations
    emergency_phrases = [
        "seek emergency care", 
        "call 911", 
        "go to the emergency room", 
        "requires immediate medical attention",
        "medical emergency",
        "seek immediate medical attention"
    ]
    
    is_emergency = any(phrase in response_text.lower() for phrase in emergency_phrases)
    
    # Process JSON responses - updated to handle both triple backtick and custom <json> tags
    json_match = re.search(r'```json\s*(.*?)\s*```|<json>\s*(.*?)\s*</json>|({[\s\S]*"assessment"[\s\S]*})', response_text, re.DOTALL)
    
    if json_match:
        try:
            # Find which group matched (could be group 1, 2, or 3)
            json_str = None
            for i in range(1, 4):
                try:
                    if json_match.group(i):
                        json_str = json_match.group(i).strip()
                        break
                except IndexError:
                    continue
                    
            if not json_str:
                logger.warning("No JSON content found in match groups")
                # Fall back to treating as a regular response
            else:
                assessment_data = json.loads(json_str)
                assessment_data["is_assessment"] = True
                assessment_data["is_question"] = False
                
                # If emergency was detected, ensure triage level is set to SEVERE
                if is_emergency and "assessment" in assessment_data:
                    assessment_data["assessment"]["triage_level"] = "SEVERE"
                    if "care_recommendation" not in assessment_data["assessment"] or not assessment_data["assessment"]["care_recommendation"]:
                        assessment_data["assessment"]["care_recommendation"] = "Seek immediate medical attention."
                
                return assessment_data
        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to parse JSON: {e}")
            # Continue to process as a regular response
    
    # Handle emergency text responses
    if is_emergency:
        return {
            "is_assessment": True,
            "is_question": False,
            "possible_conditions": response_text.strip(),
            "triage_level": "SEVERE",
            "care_recommendation": "Seek immediate medical attention."
        }
    
    # Determine if this is a question or final assessment
    contains_question = "?" in response_text
    
    # For simple responses like "I have a rash", treat them as questions
    if contains_question:
        return {
            "is_assessment": False, 
            "is_question": True, 
            "question": response_text.strip()
        }
    else:
        return {
            "is_assessment": False, 
            "is_question": False, 
            "possible_conditions": response_text.strip()
        }