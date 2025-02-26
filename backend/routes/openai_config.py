import re
import json
import logging
from typing import Dict, List, Optional, Union
from flask import current_app

# Set up logging with detailed format
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constants for confidence levels and response formatting
MIN_CONFIDENCE = 50
MAX_CONFIDENCE = 98
DEFAULT_CONFIDENCE = 75

SYSTEM_PROMPT = """You are Michele, an AI medical assistant trained to have conversations like a doctor's visit. Your goal is to understand the user's symptoms through a conversation before providing any potential diagnosis.

CONVERSATION FLOW:
1. Begin by asking about symptoms if the user hasn't provided them.
2. ALWAYS ask follow-up questions about the symptoms ONE AT A TIME. Never combine multiple questions in a single message.
3. Only after gathering sufficient information, provide a structured response with potential conditions.

CRITICAL RULES:
1. NEVER ask more than one question in a single message. For example, do not ask "How long have you had this and how severe is it?" - these must be separate messages.
2. If you need multiple pieces of information, ask for them in separate, sequential messages.
3. Wait for the user to respond to each question before asking the next one.
4. CAREFULLY review the conversation history before asking questions to avoid redundancy.

IMPORTANT CONTEXT RULES:
- CAREFULLY review the conversation history before asking questions
- NEVER ask about information the user has already provided (e.g., if they said they "woke up with a symptom", don't ask how long they've had it)
- AVOID redundant questions that repeat what the user has already told you
- ACKNOWLEDGE the information they've already shared before asking for new details

RESPONSE FORMATS:
- During information gathering: Ask ONE clear, focused question without providing any diagnosis. Format as a simple question without any JSON structure.
- For final assessment only: Provide a structured JSON response with potential conditions.

FINAL ASSESSMENT FORMAT:
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

IMPORTANT RULES:
1. NEVER provide a diagnosis or assessment until you've asked at least 2-3 follow-up questions.
2. ALWAYS use plain text for questions during information gathering.
3. ONLY use the JSON format for your final assessment.
4. If the user provides new symptoms after your assessment, restart the questioning process.
5. For emergencies (difficulty breathing, severe chest pain, etc.), immediately recommend seeking emergency care.

Remember: Your primary goal is to simulate a thoughtful medical conversation before offering any potential diagnosis.
"""

class ResponseSection:
    """Constants for response section labels"""
    CONDITIONS = "Possible Conditions:"
    CONFIDENCE = "Confidence Level:"
    CARE = "Care Recommendation:"

def calculate_confidence(response: str) -> int:
    """Calculate confidence score based on response content and key phrases."""
    response_lower = response.lower()
    
    if "clear, definitive" in response_lower:
        return 98
    elif "very likely" in response_lower:
        return 95
    elif "most likely" in response_lower:
        return 85
    elif "multiple possible conditions" in response_lower:
        return 75
    elif "suggests" in response_lower or "could be" in response_lower:
        return 65
    elif "uncertain" in response_lower or "unclear" in response_lower:
        return 50
    else:
        return DEFAULT_CONFIDENCE

def clean_ai_response(response_text: str) -> Union[Dict, str]:
    """
    Process the AI response to determine if it's a question or a structured assessment.
    
    Args:
        response_text (str): The raw response from the OpenAI API
        
    Returns:
        dict: Either a question dict or a parsed assessment dict
    """
    if not isinstance(response_text, str) or not response_text.strip():
        logger.warning("Invalid or empty response")
        return create_default_response()
    
    logger.info(f"Processing AI response: {response_text[:100]}...")
    
    # Check if the response contains JSON
    json_match = re.search(r'```json\s*(.*?)\s*```|({[\s\S]*"assessment"[\s\S]*})', 
                          response_text, re.DOTALL)
    
    if json_match:
        # This is likely a final assessment
        try:
            json_str = json_match.group(1) or json_match.group(2)
            json_str = json_str.strip()
            assessment_data = json.loads(json_str)
            
            # Add a flag to indicate this is an assessment
            assessment_data["is_assessment"] = True
            assessment_data["is_question"] = False
            logger.info("Successfully parsed assessment JSON")
            return assessment_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            # Fall back to treating as a question or using legacy format
    
    # Check if this is using the old format with "Possible Conditions:"
    has_structured_format = re.search(r'Possible Conditions:', response_text, re.IGNORECASE)
    
    if has_structured_format:
        # Process using the legacy format parser
        return process_legacy_format(response_text)
    
    # If we're here, it's a follow-up question
    contains_question = "?" in response_text
    return {
        "is_assessment": False,
        "is_question": contains_question,
        "question": response_text.strip()
    }

def process_legacy_format(response: str) -> Dict:
    """Process responses in the old format with Possible Conditions, Confidence Level, etc."""
    # Extract sections using more lenient regex
    sections = {
        'conditions': None,
        'confidence': None,
        'care': None
    }

    # Look for conditions with more flexible pattern
    conditions_match = re.search(r'(?:Possible Conditions:)?\s*(.+?)(?=(?:Confidence Level:|Care Recommendation:|$))', response, re.DOTALL)
    confidence_match = re.search(r'Confidence Level:\s*(\d+)', response)
    care_match = re.search(r'Care Recommendation:\s*(mild|moderate|severe)', response, re.IGNORECASE)

    # Validate and store each section
    if conditions_match and conditions_match.group(1).strip():
        sections['conditions'] = conditions_match.group(1).strip()
        calculated_confidence = calculate_confidence(sections['conditions'])
    else:
        # Only use "Unable to determine" if we truly can't find any meaningful content
        raw_text = response.strip()
        if raw_text and not raw_text.lower().startswith('unable to'):
            sections['conditions'] = raw_text
            calculated_confidence = calculate_confidence(raw_text)
        else:
            sections['conditions'] = "Unable to determine conditions"
            calculated_confidence = DEFAULT_CONFIDENCE

    # Handle confidence values
    explicit_confidence = int(confidence_match.group(1)) if confidence_match else calculated_confidence
    confidence_value = max(
        calculated_confidence,
        min(MAX_CONFIDENCE, max(MIN_CONFIDENCE, explicit_confidence))
    )

    # Handle care recommendation
    if care_match:
        care_value = care_match.group(1).lower()
    else:
        # Default to moderate unless we have clear indicators
        if "severe" in response.lower() or "emergency" in response.lower():
            care_value = 'severe'
        elif "mild" in response.lower() or "minor" in response.lower():
            care_value = 'mild'
        else:
            care_value = 'moderate'
    
    # Create assessment in the new format
    assessment_data = {
        "is_assessment": True,
        "is_question": False,
        "assessment": {
            "conditions": [
                {"name": sections['conditions'], "confidence": confidence_value}
            ],
            "triage_level": care_value.upper(),
            "care_recommendation": f"Based on the assessment, this appears to be a {care_value} condition.",
            "disclaimer": "This assessment is for informational purposes only and does not replace professional medical advice."
        }
    }
    
    logger.info("Processed legacy format into structured assessment")
    return assessment_data

def create_default_response() -> Dict:
    """Create a default response when the AI response is invalid or empty."""
    return {
        "is_assessment": True,
        "is_question": False,
        "assessment": {
            "conditions": [
                {"name": "Unable to analyze symptoms at this time", "confidence": DEFAULT_CONFIDENCE}
            ],
            "triage_level": "MODERATE",
            "care_recommendation": "Consider consulting with a healthcare professional if symptoms persist.",
            "disclaimer": "This assessment is for informational purposes only and does not replace professional medical advice."
        }
    }