import re
import logging
from typing import Dict, List, Optional

# Set up logging with detailed format
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constants for confidence levels and response formatting
MIN_CONFIDENCE = 75
MAX_CONFIDENCE = 95
DEFAULT_CONFIDENCE = 75

SYSTEM_PROMPT = """You are HealthTracker AI, an advanced medical screening assistant.

CONVERSATION GUIDELINES:
- Listen carefully to the patient's description.
- Ask only one follow-up question at a time.
- Focus on the most relevant symptoms first.

REQUIRED OUTPUT FORMAT (EXACTLY AS SHOWN):
Possible Conditions: [List primary condition first, then alternatives if any]
Confidence Level: [single number 75-95]
Care Recommendation: [must be one of: mild, moderate, severe]

CRITICAL FORMATTING RULES:
- MUST include all three sections in exact order shown above
- Each section MUST be on its own line
- NO additional sections or text allowed
- NO asterisks or markdown
- NO bullet points or lists
- NO explanatory text between sections
- Keep responses brief and clear

RESPONSE GUIDELINES:
- Confidence Level must be a single number between 75-95
- Care Recommendation must be exactly 'mild', 'moderate', or 'severe'
- Possible Conditions should be clear and concise
- No diagnostic language (e.g., "it might be" or "possibly")
- No medical advice beyond basic triage level

EXAMPLE RESPONSE:
Possible Conditions: Tension headache with possible dehydration
Confidence Level: 85
Care Recommendation: mild

This tool does not provide medical diagnoses. Always consult a doctor for medical concerns."""

class ResponseSection:
    """Constants for response section labels"""
    CONDITIONS = "Possible Conditions:"
    CONFIDENCE = "Confidence Level:"
    CARE = "Care Recommendation:"

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

    # Look for each section with strict formatting
    conditions_match = re.search(r'Possible Conditions:\s*(.+?)(?=\nConfidence Level:|$)', response, re.DOTALL)
    confidence_match = re.search(r'Confidence Level:\s*(\d+)', response)
    care_match = re.search(r'Care Recommendation:\s*(mild|moderate|severe)', response, re.IGNORECASE)

    # Validate and store each section
    if conditions_match:
        sections['conditions'] = conditions_match.group(1).strip()
    if confidence_match:
        confidence = int(confidence_match.group(1))
        sections['confidence'] = str(max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence)))
    if care_match:
        sections['care'] = care_match.group(1).lower()

    # If any section is missing, use defaults
    if not all(sections.values()):
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