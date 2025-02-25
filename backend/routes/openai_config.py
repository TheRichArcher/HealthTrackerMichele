import re
import logging
from typing import Dict, List, Optional

# Set up logging with detailed format
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constants for confidence levels and response formatting
MIN_CONFIDENCE = 50
MAX_CONFIDENCE = 98
DEFAULT_CONFIDENCE = 75

SYSTEM_PROMPT = """You are HealthTracker AI, an advanced medical screening assistant that mimics a doctor's visit.

YOUR PRIMARY GOAL:
- Build a conversation with the patient by asking follow-up questions
- NEVER provide an immediate diagnosis on the first response
- Only provide a final assessment after gathering sufficient information

CONVERSATION FLOW:
1. Patient shares initial symptom
2. YOU ASK FOLLOW-UP QUESTIONS (at least 2-3) about:
   * Duration/timing
   * Severity
   * Associated symptoms
   * Triggers or patterns
   * Impact on daily life
3. Only after gathering sufficient information, provide a final assessment

CRITICAL RULES:
- For ANY initial symptom, ALWAYS respond with a follow-up question first
- DO NOT provide "Possible Conditions" in your first 2-3 responses
- Ask ONLY ONE question at a time
- Maintain a natural, conversational tone
- Never provide definitive medical diagnosis

RESPONSE FORMAT:
- For follow-up questions: Just ask a natural question without any special formatting
- For final assessment only (after sufficient information):
  Possible Conditions: [Your analysis here]
  Confidence Level: [number between 50-98]
  Care Recommendation: [mild/moderate/severe]

🚨 EMERGENCY PROTOCOL:
- If symptoms suggest immediate danger (chest pain, breathing difficulty, severe confusion):
  * Immediately recommend emergency care
  * Skip normal conversation flow"""

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

def clean_ai_response(response: Optional[str]) -> str:
    """Clean and validate AI response format."""
    if not isinstance(response, str) or not response.strip():
        logger.warning("Invalid or empty response")
        return create_default_response()

    logger.debug("Original AI response: %s", response)
    
    # Check if this is a conversational response (a question or doesn't have the structured format)
    has_question = '?' in response
    has_structured_format = re.search(r'Possible Conditions:', response, re.IGNORECASE)
    
    if has_question or not has_structured_format:
        logger.info("Detected conversational response")
        # Return the response without structured format
        return response.strip()

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
    sections['confidence'] = str(max(
        calculated_confidence,
        min(MAX_CONFIDENCE, max(MIN_CONFIDENCE, explicit_confidence))
    ))

    # Handle care recommendation
    if care_match:
        sections['care'] = care_match.group(1).lower()
    else:
        # Default to moderate unless we have clear indicators
        if "severe" in response.lower() or "emergency" in response.lower():
            sections['care'] = 'severe'
        elif "mild" in response.lower() or "minor" in response.lower():
            sections['care'] = 'mild'
        else:
            sections['care'] = 'moderate'

    # If essential sections are missing, use defaults
    if not sections['conditions'] or not sections['confidence'] or not sections['care']:
        logger.warning("Missing sections in response: %s", 
                      [k for k, v in sections.items() if not v])
        return create_default_response()

    # Construct properly formatted response
    formatted_response = (
        f"Possible Conditions: {sections['conditions']}\n"
        f"Confidence Level: {sections['confidence']}\n"
        f"Care Recommendation: {sections['care']}"
    )

    logger.debug("Cleaned response: %s", formatted_response)
    return formatted_response

def create_default_response() -> str:
    """Create a default response when the AI response is invalid or empty."""
    return (
        "Possible Conditions: Unable to analyze symptoms at this time\n"
        f"Confidence Level: {DEFAULT_CONFIDENCE}\n"
        "Care Recommendation: moderate"
    )