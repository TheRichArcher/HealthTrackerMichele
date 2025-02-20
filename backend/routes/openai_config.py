import re
import logging
from typing import Dict, List, Optional

# Set up logging with more detailed format
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

STRICT OUTPUT FORMAT:
Possible Conditions: [your analysis]
Confidence Level: [number between 75-95]
Care Recommendation: [your recommendation]

CRITICAL FORMATTING RULES:
- NO asterisks (*) or double asterisks (**) anywhere in the response
- NO markdown formatting of any kind
- NO special characters or symbols
- NO bullet points or lists
- NO headers or separators
- Use plain text only
- Use single newlines between sections
- Keep responses brief and clear

DIAGNOSTIC APPROACH:
1. Primary Condition assessment (75-95% confidence based on certainty)
2. Alternative possibilities with explanations
3. Triage levels (mild/moderate/severe) based on symptoms

IMPORTANT RESTRICTIONS:
- Do not provide a definitive diagnosis
- Do not use complex medical jargon
- Do not reference external sources
- Do not use conditional language (e.g., "it might be")
- Keep responses concise and relevant
- Always use numerical values for confidence (75-95)

DISCLAIMER:
This tool does not provide medical diagnoses. Always consult a doctor for medical concerns."""

class ResponseSection:
    """Constants for response section labels"""
    CONDITIONS = "Possible Conditions:"
    CONFIDENCE = "Confidence Level:"
    CARE = "Care Recommendation:"

def clean_ai_response(response: Optional[str]) -> str:
    """
    Remove all formatting and clean up whitespace in AI responses.
    
    Args:
        response (str): Raw response from OpenAI
        
    Returns:
        str: Cleaned and validated response
    """
    if not response:
        logger.warning("Received empty response")
        return create_default_response()
    
    logger.debug("Original AI response: %s", response)
    
    # Define cleaning patterns with their purposes
    patterns: List[tuple] = [
        (r'\*\*([^*]+)\*\*', r'\1'),  # Remove **bold**
        (r'\*([^*]+)\*', r'\1'),      # Remove *italic*
        (r'_([^_]+)_', r'\1'),        # Remove _italic_
        (r'`([^`]+)`', r'\1'),        # Remove `code`
        (r'#\s*', ''),                # Remove markdown headers
        (r'^\s*[-•]\s*', ''),         # Remove bullet points at start of lines
        (r'\n\s*[-•]\s*', '\n'),      # Remove bullet points after newlines
        (r'[\[\]]+', ''),             # Remove square brackets
        (r'\s+', ' '),                # Normalize all whitespace
    ]

    cleaned = response
    for pattern, replacement in patterns:
        before_cleaning = cleaned
        cleaned = re.sub(pattern, replacement, cleaned)
        if before_cleaning != cleaned:
            logger.debug("Applied pattern %s", pattern)

    # Normalize whitespace more aggressively
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)  # Remove empty lines
    cleaned = re.sub(r' *\n *', '\n', cleaned)   # Clean up around newlines
    cleaned = cleaned.strip()

    logger.debug("After initial cleaning: %s", cleaned)
    
    # Validate and ensure required format
    cleaned = validate_ai_format(cleaned)
    
    logger.debug("Final formatted response: %s", cleaned)
    return cleaned

def validate_ai_format(response: str) -> str:
    """
    Ensure AI response follows the expected format and contains all required sections.
    
    Args:
        response (str): Cleaned response string
        
    Returns:
        str: Validated and properly formatted response
    """
    required_sections = {
        ResponseSection.CONDITIONS: "Unable to determine conditions",
        ResponseSection.CONFIDENCE: str(DEFAULT_CONFIDENCE),
        ResponseSection.CARE: "moderate"
    }
    
    # Check for missing sections
    for section, default_value in required_sections.items():
        if section not in response:
            logger.warning("Missing section: %s", section)
            response += f"\n{section} {default_value}"

    # Ensure proper spacing after section labels
    for section in required_sections:
        response = re.sub(fr"{section}(?!\s)", f"{section} ", response)
    
    # Handle confidence level
    confidence_match = re.search(r"Confidence Level:\s*(\d+)", response)
    if not confidence_match:
        logger.warning("No valid confidence level found")
        response = re.sub(r"Confidence Level:.*", f"Confidence Level: {DEFAULT_CONFIDENCE}", response)
    else:
        confidence = int(confidence_match.group(1))
        if confidence < MIN_CONFIDENCE or confidence > MAX_CONFIDENCE:
            logger.warning("Confidence %d out of range [%d-%d]", confidence, MIN_CONFIDENCE, MAX_CONFIDENCE)
            confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence))
            response = re.sub(r"Confidence Level:\s*\d+", f"Confidence Level: {confidence}", response)
    
    return response

def create_default_response() -> str:
    """Create a default response when the AI response is invalid or empty."""
    return (
        "Possible Conditions: Unable to analyze symptoms at this time\n"
        f"Confidence Level: {DEFAULT_CONFIDENCE}\n"
        "Care Recommendation: moderate"
    )