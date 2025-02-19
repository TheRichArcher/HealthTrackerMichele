# backend/routes/openai_config.py

import re
import logging

# Set up logging
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are HealthTracker AI, an advanced medical screening assistant.

CONVERSATION GUIDELINES:
- Listen carefully to the patient's description.
- Ask only one follow-up question at a time.
- Focus on the most relevant symptoms first.

STRICT OUTPUT FORMAT:
Possible Conditions: [your analysis]
Confidence Level: [number between 75-95]
Care Recommendation: [your recommendation]

FORMATTING RULES (CRITICAL):
- Use ONLY plain text (no markdown, symbols, or special characters)
- NO lists, bullet points, bold, italics, or brackets
- NO headings, separators, or emojis
- Use single newlines only (no extra spacing)
- Answer briefly and clearly

DIAGNOSTIC APPROACH:
- Primary Condition assessment (75-95% confidence based on certainty)
- Alternative possibilities with explanations
- Triage levels (mild/moderate/severe) based on symptoms

IMPORTANT RESTRICTIONS:
- Do not provide a definitive diagnosis
- Do not use complex medical jargon
- Do not reference external sources
- Do not use conditional language (e.g., "it might be")
- Keep responses concise and relevant
- Always use numerical values for confidence (75-95)

DISCLAIMER:
This tool does not provide medical diagnoses. Always consult a doctor for medical concerns."""

def clean_ai_response(response):
    """Remove all formatting and clean up whitespace in AI responses."""
    if not response:
        return ""
    
    logger.debug(f"Original AI response: {response}")
    
    patterns = [
        (r'\*\*([^*]+)\*\*', r'\1'),  # Remove **bold**
        (r'\*([^*]+)\*', r'\1'),      # Remove *italic*
        (r'_([^_]+)_', r'\1'),        # Remove _italic_
        (r'`([^`]+)`', r'\1'),        # Remove `code`
        (r'#\s*', ''),                # Remove markdown headers
        (r'^\s*[-•]\s*', ''),         # Remove bullet points at start of lines
        (r'\n\s*[-•]\s*', '\n'),      # Remove bullet points after newlines
        (r'[\[\]]+', '')              # Remove square brackets
    ]

    cleaned = response
    for pattern, replacement in patterns:
        matches = re.findall(pattern, cleaned)
        if matches:
            logger.debug(f"Removing {matches} using pattern {pattern}")
        cleaned = re.sub(pattern, replacement, cleaned)

    # Normalize whitespace
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)  # Remove empty lines
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)     # Normalize spaces and tabs
    cleaned = re.sub(r' *\n *', '\n', cleaned)    # Clean up around newlines
    cleaned = cleaned.strip()                      # Remove leading/trailing whitespace

    logger.debug(f"After cleaning: {cleaned}")
    
    # Validate and ensure required format
    cleaned = validate_ai_format(cleaned)
    
    logger.debug(f"Final formatted response: {cleaned}")
    return cleaned

def validate_ai_format(response):
    """Ensure AI response follows the expected format."""
    required_labels = [
        "Possible Conditions:",
        "Confidence Level:",
        "Care Recommendation:"
    ]
    
    # Check for missing labels and add them if necessary
    for label in required_labels:
        if label not in response:
            logger.warning(f"Missing expected label: {label}")
            if label == "Confidence Level:":
                response += f"\n{label} 75"  # Default confidence
            else:
                response += f"\n{label} Unable to determine"

    # Ensure proper spacing after labels
    for label in required_labels:
        response = re.sub(f"{label}(?!\s)", f"{label} ", response)
    
    # Ensure Confidence Level is a number between 75-95
    confidence_match = re.search(r"Confidence Level:\s*(\d+)", response)
    if not confidence_match:
        logger.warning("Non-numeric confidence level found, setting to default 75")
        response = re.sub(r"Confidence Level:.*", "Confidence Level: 75", response)
    else:
        confidence = int(confidence_match.group(1))
        if confidence < 75 or confidence > 95:
            logger.warning(f"Confidence {confidence} out of range, adjusting to valid range")
            confidence = max(75, min(95, confidence))
            response = re.sub(r"Confidence Level:\s*\d+", f"Confidence Level: {confidence}", response)
    
    return response