import re
import logging
from typing import Dict, List, Optional, Any

# Set up logging with detailed format
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constants for confidence levels and response formatting
MIN_CONFIDENCE = 50
MAX_CONFIDENCE = 98
DEFAULT_CONFIDENCE = 75

SYSTEM_PROMPT = """You are HealthTracker AI, an advanced medical screening assistant. Analyze the symptoms and provide a structured response in EXACTLY this format:

RESPONSE FORMAT:
Possible Conditions: [List the most likely conditions based on symptoms]
Confidence Level: [A number between 50-98]
Care Recommendation: [mild/moderate/severe]

GUIDELINES:
1. For Possible Conditions:
   - List 1-3 most likely conditions
   - Use clear, concise language
   - Include brief explanations
   - For multiple conditions, separate with semicolons
   - Include severity indicators when relevant

2. For Confidence Level:
   - 98: Nearly certain diagnosis with clear symptoms
   - 85-95: Very likely diagnosis with strong indicators
   - 75-84: Likely diagnosis with typical symptoms
   - 50-74: Possible diagnosis with limited information

3. For Care Recommendation:
   - mild: Can be managed at home with self-care
   - moderate: Should see a doctor within next few days
   - severe: Needs immediate medical attention

CONVERSATION GUIDELINES:
- Listen carefully to the patient's description
- Ask natural follow-up questions based on responses
- Focus on the most relevant symptoms first
- Gather key information through conversation:
  * Timing/duration when relevant
  * Severity when needed
  * Specific triggers or patterns
  * Associated symptoms
  * Impact on daily activities

EMERGENCY PROTOCOL:
If symptoms suggest immediate danger (chest pain, breathing difficulty, severe confusion):
- Set Confidence Level to 98
- Set Care Recommendation to severe
- Include "URGENT:" prefix in conditions
- Immediately recommend emergency care
- Skip normal conversation flow

CRITICAL RULES:
- Ask ONLY ONE question at a time
- Maintain a natural, conversational tone
- Never provide definitive medical diagnosis
- Clearly explain reasoning for recommendations
- Always include confidence level and care recommendation

Example response:
Possible Conditions: Common cold with upper respiratory symptoms, including nasal congestion and sore throat; Possible seasonal allergies based on environmental factors
Confidence Level: 85
Care Recommendation: mild"""

class ResponseSection:
    """Constants for response section labels"""
    CONDITIONS = "Possible Conditions:"
    CONFIDENCE = "Confidence Level:"
    CARE = "Care Recommendation:"

def calculate_confidence(conditions: str) -> int:
    """Calculate confidence score based on response content and key phrases."""
    conditions_lower = conditions.lower()
    
    # Emergency/urgent conditions always get highest confidence
    if "urgent:" in conditions_lower:
        return 98
        
    # Very clear conditions with strong indicators
    if any(phrase in conditions_lower for phrase in [
        "clear indicators",
        "strong evidence",
        "very likely",
        "clear pattern",
        "definite signs"
    ]):
        return 90
        
    # Likely conditions with good supporting evidence
    if any(phrase in conditions_lower for phrase in [
        "likely",
        "typical symptoms",
        "consistent with",
        "matches pattern"
    ]):
        return 80
        
    # Possible conditions with some supporting evidence
    if any(phrase in conditions_lower for phrase in [
        "suggests",
        "could be",
        "possibly",
        "may indicate"
    ]):
        return 70
        
    # Less certain conditions
    if any(phrase in conditions_lower for phrase in [
        "unclear",
        "uncertain",
        "multiple possibilities",
        "need more information"
    ]):
        return 60
        
    # Very uncertain or minimal information
    if any(phrase in conditions_lower for phrase in [
        "unable to determine",
        "insufficient information",
        "too vague",
        "cannot assess"
    ]):
        return 50
        
    return DEFAULT_CONFIDENCE

def clean_ai_response(response: str) -> Dict[str, Any]:
    """Clean and structure AI response."""
    try:
        logger.debug(f"Raw AI response: {response}")
        
        # Extract sections using more precise patterns
        conditions_pattern = r"Possible Conditions:\s*(.+?)(?=Confidence Level:|$)"
        confidence_pattern = r"Confidence Level:\s*(\d+)"
        care_pattern = r"Care Recommendation:\s*(mild|moderate|severe)"
        
        # Extract each section
        conditions_match = re.search(conditions_pattern, response, re.DOTALL)
        confidence_match = re.search(confidence_pattern, response)
        care_match = re.search(care_pattern, response, re.IGNORECASE)
        
        # Process conditions
        conditions = conditions_match.group(1).strip() if conditions_match else "Unable to determine conditions"
        
        # Process confidence
        confidence = DEFAULT_CONFIDENCE
        if confidence_match:
            try:
                explicit_confidence = int(confidence_match.group(1))
                calculated_confidence = calculate_confidence(conditions)
                # Use the higher of the explicit or calculated confidence
                confidence = max(
                    calculated_confidence,
                    min(MAX_CONFIDENCE, max(MIN_CONFIDENCE, explicit_confidence))
                )
            except ValueError:
                logger.warning("Invalid confidence value, using calculated confidence")
                confidence = calculate_confidence(conditions)
        else:
            confidence = calculate_confidence(conditions)
        
        # Process care recommendation
        care = care_match.group(1).lower() if care_match else "moderate"
        
        # Adjust care recommendation based on confidence and conditions
        if "urgent:" in conditions.lower() or confidence >= 95:
            care = "severe"
        elif confidence < 60:
            care = "moderate"  # Default to moderate if confidence is low
        
        # Construct formatted response
        formatted_response = {
            "possible_conditions": conditions,
            "confidence": confidence,
            "care_recommendation": care
        }
        
        logger.debug(f"Formatted response: {formatted_response}")
        return formatted_response
        
    except Exception as e:
        logger.error(f"Error cleaning AI response: {str(e)}")
        return create_default_response()

def create_default_response() -> Dict[str, Any]:
    """Create a default response when the AI response is invalid or empty."""
    return {
        "possible_conditions": "Unable to analyze symptoms at this time",
        "confidence": DEFAULT_CONFIDENCE,
        "care_recommendation": "moderate"
    }

def validate_response_format(response: Dict[str, Any]) -> bool:
    """Validate that the response contains all required fields with valid values."""
    try:
        required_fields = {
            "possible_conditions": str,
            "confidence": int,
            "care_recommendation": str
        }
        
        for field, field_type in required_fields.items():
            if field not in response:
                logger.error(f"Missing required field: {field}")
                return False
            if not isinstance(response[field], field_type):
                logger.error(f"Invalid type for field {field}: expected {field_type}, got {type(response[field])}")
                return False
                
        if not MIN_CONFIDENCE <= response["confidence"] <= MAX_CONFIDENCE:
            logger.error(f"Confidence score out of range: {response['confidence']}")
            return False
            
        if response["care_recommendation"] not in ["mild", "moderate", "severe"]:
            logger.error(f"Invalid care recommendation: {response['care_recommendation']}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error validating response format: {str(e)}")
        return False