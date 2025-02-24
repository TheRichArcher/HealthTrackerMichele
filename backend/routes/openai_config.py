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

SYSTEM_PROMPT = """You are HealthTracker AI, an advanced medical screening assistant.

CONVERSATION GUIDELINES:
- Listen carefully to the patient's description.
- Ask natural follow-up questions based on what they tell you.
- Focus on the most relevant symptoms first.
- Gather key information through conversation:
  * Timing/duration when relevant
  * Severity when needed
  * Specific triggers or patterns
  * Associated symptoms
  * Impact on daily activities

DIAGNOSTIC APPROACH:
- Primary Condition assessment (50-98% confidence based on certainty)
- Alternative possibilities with explanations
- Triage levels (mild/moderate/severe) based on symptoms

🚨 EMERGENCY PROTOCOL:
- If symptoms suggest immediate danger (chest pain, breathing difficulty, severe confusion):
  * Immediately recommend emergency care
  * Skip normal conversation flow

CRITICAL RULES:
- Ask ONLY ONE question at a time and wait for the patient's response
- Maintain a natural, conversational tone
- Ask questions that flow logically from patient responses
- Never provide definitive medical diagnosis
- Clearly explain reasoning for recommendations

REQUIRED RESPONSE FORMAT:
Possible Conditions: [Your analysis here]
Confidence Level: [number between 50-98]
Care Recommendation: [mild/moderate/severe]

Use phrases like "most likely", "very likely", or "multiple possible conditions" to help determine confidence."""

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

    # Extract sections using more precise regex
    sections = {
        'conditions': None,
        'confidence': None,
        'care': None
    }

    # Initialize confidence values
    calculated_confidence = DEFAULT_CONFIDENCE

    # Look for each section with strict formatting
    conditions_match = re.search(r'Possible Conditions:\s*(.+?)(?=\nConfidence Level:|$)', response, re.DOTALL)
    confidence_match = re.search(r'Confidence Level:\s*(\d+)', response)
    care_match = re.search(r'Care Recommendation:\s*(mild|moderate|severe)', response, re.IGNORECASE)

    # Validate and store each section
    if conditions_match:
        sections['conditions'] = conditions_match.group(1).strip()
        calculated_confidence = calculate_confidence(sections['conditions'])
    else:
        sections['conditions'] = "Unable to determine conditions"

    # Handle confidence values
    explicit_confidence = int(confidence_match.group(1)) if confidence_match else MIN_CONFIDENCE
    sections['confidence'] = str(max(
        calculated_confidence,
        min(MAX_CONFIDENCE, max(MIN_CONFIDENCE, explicit_confidence))
    ))

    if care_match:
        sections['care'] = care_match.group(1).lower()
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