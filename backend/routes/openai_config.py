import re
import json
import logging
from typing import Dict, Union
from flask import current_app
from backend.config import Config  # Ensures API key handling aligns with config.py
from backend.models import UserTierEnum  # Required for checking user tier

# Set up logging with detailed format
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constants for confidence levels and response formatting
MIN_CONFIDENCE = 10  # Allowing lower confidence for nuanced assessments
MAX_CONFIDENCE = 95  # Preventing overconfidence
DEFAULT_CONFIDENCE = 75
MIN_CONFIDENCE_THRESHOLD = 90  # Increased from 85% to 90% to prevent premature assessments
QUESTION_COUNT_THRESHOLD = 5  # Minimum number of questions before assessment

# Lists for condition severity validation - keeping these minimal
MILD_CONDITION_PHRASES = [
    "common cold", "seasonal allergy", "mild", "minor", "viral infection",
    "sunburn"  # Explicitly add sunburn
]

# Common conditions that shouldn't trigger upgrade prompts even with doctor recommendations
# Keeping this list minimal and focused on truly common conditions
COMMON_CONDITIONS_NO_UPGRADE = [
    "common cold", "seasonal allergy", "mild headache", "tension headache",
    "sinus infection", "sinusitis", "sore throat", 
    "stomach flu", "diarrhea", "constipation",
    "urinary tract infection", "uti", "pink eye",
    "sunburn"
]

# Potentially serious conditions that require more thorough questioning
SERIOUS_CONDITIONS_REQUIRING_DIFFERENTIATION = [
    "heat exhaustion", "heat stroke", "dehydration", "concussion", "migraine", 
    "meningitis", "stroke", "heart attack", "pulmonary embolism", "sepsis",
    "diabetic ketoacidosis", "anaphylaxis", "appendicitis"
]

# Specific follow-up questions for ambiguous or uncertain answers
CLARIFYING_QUESTIONS = {
    "dehydration_heat": [
        "I need to be certain: Have you felt extremely hot or sweaty, or have you stopped sweating?",
        "Do you feel confused or disoriented?",
        "Have you felt nauseous or vomited since the symptoms started?",
        "Is your skin cool and clammy, or hot and dry?"
    ],
    "head_injury": [
        "I need to be certain: Have you experienced any loss of consciousness, even briefly?",
        "Are you experiencing any confusion, memory problems, or difficulty concentrating?",
        "Do you have a headache that is getting worse over time?",
        "Have you noticed any changes in your vision or pupils?"
    ],
    "chest_pain": [
        "I need to be certain: Does the pain radiate to your arm, jaw, or back?",
        "Are you experiencing shortness of breath along with the chest pain?",
        "Are you sweating, nauseous, or lightheaded with the pain?",
        "Do you have a history of heart problems or high blood pressure?"
    ],
    "uncertain": [
        "I understand you're not sure, but this is important for your safety. Could you try to describe any other symptoms you've noticed?",
        "When you say you're not sure, is it because you haven't checked, or because the symptom is unclear?",
        "For your safety, I need to rule out serious conditions. Have you experienced any severe symptoms like extreme confusion, fainting, or severe pain?"
    ]
}

# Updated system prompt to leverage OpenAI's capabilities and enforce proper formatting
SYSTEM_PROMPT = """You are Michele, an AI medical assistant trained to have conversations like a doctor's visit.
Your goal is to understand the user's symptoms through a conversation before providing any potential diagnosis.

CRITICAL INSTRUCTIONS:
1. ALWAYS ask at least 5 follow-up questions before considering a diagnosis.
2. For potentially serious conditions (like heat exhaustion vs. heat stroke, dehydration, concussion, etc.), ask at least 7-8 questions to properly differentiate between similar conditions.
3. ALWAYS provide specific condition names (e.g., 'Gallstones', 'Acid Reflux', 'Migraine') rather than general categories (e.g., 'Digestive Issue', 'Headache').
4. When providing a diagnosis, ALWAYS include both the medical term and common name in this format: "Medical Term (Common Name)" - for example "Cholelithiasis (Gallstones)" or "Cephalgia (Headache)".
5. NEVER provide a diagnosis until you've asked enough questions to be at least 90% confident.
6. ALWAYS include confidence levels with any diagnosis.
7. NEVER use placeholder names like "Condition 1" or "Medical Condition" - always use specific medical terminology.
8. If you're not confident (below 90%), continue asking questions instead of providing an assessment.

HANDLING UNCERTAIN ANSWERS:
When a user responds with uncertain answers like "I'm not sure", "maybe", or "I don't know":
1. DO NOT proceed with an assessment
2. Ask more specific, direct questions that can be answered with simple yes/no
3. For heat-related or dehydration symptoms, ALWAYS ask about:
   - Body temperature (hot/normal/cold)
   - Skin condition (dry/wet/clammy)
   - Mental status (confused/alert/disoriented)
   - Sweating patterns (stopped sweating/sweating profusely)
4. Explain why these questions are important for their safety

CRITICAL DIFFERENTIATION REQUIREMENTS:
When symptoms suggest potentially serious conditions that require differentiation (like heat exhaustion vs. heat stroke, or dehydration vs. more serious conditions), you MUST:
1. Ask specific questions to differentiate between similar conditions
2. For heat-related issues: Ask about body temperature, mental status changes, sweating patterns
3. For head injuries: Ask about loss of consciousness, memory issues, nausea, pupil changes
4. For chest pain: Ask about radiation to arm/jaw, shortness of breath, sweating, nausea
5. NEVER provide a diagnosis until you've asked enough questions to properly differentiate between similar conditions

CONVERSATION FLOW:
1. Begin by asking about symptoms if the user hasn't provided them.
2. ALWAYS ask at least 5 follow-up questions before considering a diagnosis.
   - Tailor questions based on the symptom provided.
   - Do NOT ask the same set of questions for every symptom.
   - Include symptom history, triggers, and progression.
3. Once enough information is gathered, provide a structured response.

FOLLOW-UP QUESTIONING LOGIC:
- Ask about symptom onset, duration, severity, and any factors that make it better or worse
- Ask about related symptoms that might help narrow down the diagnosis
- Ask about medical history if relevant to the current symptoms
- Ask about lifestyle factors that might contribute to the symptoms
- Ask about any treatments the user has already tried

TRIAGE GUIDELINES:
- MILD: Conditions that can be managed at home with self-care (e.g., common cold, sunburn, seasonal allergies)
- MODERATE: Conditions that may benefit from medical consultation but aren't urgent (e.g., ear infection, persistent symptoms)
- SEVERE: Conditions requiring immediate medical attention (e.g., severe chest pain, difficulty breathing, signs of stroke)

For common skin conditions like sunburn, unless severe (extensive blistering, fever, severe pain), these should be classified as MILD with home care recommendations.

EMERGENCY HANDLING:
If the user describes symptoms that could indicate a medical emergency (such as chest pain, difficulty breathing, sudden severe headache, stroke symptoms, etc.):
1. Ask no more than 2 follow-up questions to confirm severity
2. If confirmed serious, IMMEDIATELY advise them to seek emergency care
3. Use phrases like "This could be serious and requires immediate medical attention"
4. Be direct and clear about the urgency
5. For chest pain especially, if it's severe, radiating, or accompanied by shortness of breath, IMMEDIATELY recommend emergency care

CONFIDENCE SCORING GUIDELINES:
- 95-99%: Clear, textbook presentation with multiple confirming symptoms
- 90-94%: Strong evidence with most confirming details present
- 80-89%: Good evidence but some uncertainty remains
- 70-79%: Moderate evidence with multiple possible conditions
- Below 70%: Limited evidence, highly uncertain

IMPORTANT RULES:
1. NEVER ask a question the user has already answered.
2. DO NOT start questions by repeating the user's response.
3. Accept single-character inputs where applicable (e.g., severity rating from 1-10).
4. If a symptom description is vague, ask for clarification instead of assuming.
5. If the user responds with "I'm not sure" or "maybe", ask more specific questions.

FINAL ASSESSMENT FORMAT:
The AI must return JSON structured like this:
<json>
{
  "assessment": {
    "conditions": [
      {"name": "Medical Term (Common Name)", "confidence": 70},
      {"name": "Alternative Medical Term (Common Name)", "confidence": 20}
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

def get_clarifying_question(response_text: str) -> str:
    """
    Returns an appropriate clarifying question based on the context of the conversation.
    """
    # Check for heat-related or dehydration context
    if any(term in response_text.lower() for term in ["heat", "hot", "dehydrat", "dizz", "faint", "weak", "sweat"]):
        questions = CLARIFYING_QUESTIONS["dehydration_heat"]
    # Check for head injury context
    elif any(term in response_text.lower() for term in ["head", "concuss", "hit", "fall", "dizz", "nause", "vomit"]):
        questions = CLARIFYING_QUESTIONS["head_injury"]
    # Check for chest pain context
    elif any(term in response_text.lower() for term in ["chest", "heart", "pain", "breath", "pressure"]):
        questions = CLARIFYING_QUESTIONS["chest_pain"]
    # Default to general uncertain questions
    else:
        questions = CLARIFYING_QUESTIONS["uncertain"]
    
    # Return a random question from the appropriate category
    import random
    return random.choice(questions)

def clean_ai_response(response_text: str, user=None) -> Union[Dict, str]:
    """
    Processes the AI response and determines if it's a question or assessment.
    Now includes subscription tier and confidence threshold enforcement.
    """
    # Log user information for debugging
    is_production = current_app.config.get("ENV") == "production" if current_app else False
    
    if user:
        logger.info(f"Processing response for user with tier: {user.subscription_tier if hasattr(user, 'subscription_tier') else 'Unknown'}")
    else:
        logger.info("Processing response for unauthenticated user (user object not provided)")
    
    if not isinstance(response_text, str) or not response_text.strip():
        logger.warning("Invalid or empty response")
        return create_default_response()
    
    logger.info(f"Processing AI response: {response_text[:100]}...")

    # Initialize confidence with default value to ensure it always exists
    confidence = DEFAULT_CONFIDENCE

    # Check for emergency recommendations
    emergency_phrases = [
        "seek emergency care", 
        "call 911", 
        "go to the emergency room", 
        "requires immediate medical attention",
        "medical emergency",
        "seek immediate medical attention"
    ]
    
    # Check for medical consultation recommendations
    medical_consultation_phrases = [
        "seek a consultation", 
        "see a doctor",
        "healthcare professional",
        "medical attention",
        "consult with",
        "visit a doctor",
        "proper diagnosis",
        "professional medical advice",
        "seek a consultation",
        "consult a doctor",
        "medical professional",
        "medical provider"
    ]
    
    # Check for uncertain responses that should trigger clarifying questions
    uncertain_phrases = [
        "not sure", "maybe", "i don't know", "uncertain", "possibly", 
        "can't tell", "hard to say", "unclear", "don't remember"
    ]
    
    is_emergency = any(phrase in response_text.lower() for phrase in emergency_phrases)
    needs_medical_attention = any(phrase in response_text.lower() for phrase in medical_consultation_phrases)
    has_uncertainty = any(phrase in response_text.lower() for phrase in uncertain_phrases)
    
    if is_emergency:
        logger.info("EMERGENCY recommendation detected in response")
    if needs_medical_attention:
        logger.info("Medical consultation recommendation detected in response")
    if has_uncertainty:
        logger.info("Uncertainty detected in response, will require clarifying questions")

    # Extract JSON-formatted response if present
    json_match = re.search(r'```json\s*(.*?)\s*```|<json>\s*(.*?)\s*</json>|({[\s\S]*"assessment"[\s\S]*})', response_text, re.DOTALL)
    
    if json_match:
        try:
            # Find and parse JSON response
            json_str = None
            for i in range(1, 4):
                try:
                    if json_match.group(i):
                        json_str = json_match.group(i).strip()
                        break
                except (IndexError, AttributeError):
                    continue
                    
            if not json_str:
                logger.warning("No JSON content found in match groups")
            else:
                logger.info(f"Found JSON content: {json_str[:100]}...")
                assessment_data = json.loads(json_str)
                assessment_data["is_assessment"] = True
                assessment_data["is_question"] = False
                
                # Get confidence level
                if "assessment" in assessment_data and "conditions" in assessment_data["assessment"]:
                    conditions = assessment_data["assessment"]["conditions"]
                    if conditions and len(conditions) > 0:
                        confidence = conditions[0].get("confidence", DEFAULT_CONFIDENCE)
                        
                        # Check if this is a potentially serious condition that requires differentiation
                        condition_name = conditions[0].get("name", "").lower()
                        requires_differentiation = any(serious_cond in condition_name for serious_cond in SERIOUS_CONDITIONS_REQUIRING_DIFFERENTIATION)
                        
                        if requires_differentiation:
                            logger.info(f"Detected potentially serious condition requiring differentiation: {condition_name}")
                            # For potentially serious conditions, we require higher confidence
                            if confidence < 95:  # Even stricter for serious conditions
                                logger.info(f"Confidence too low ({confidence}%) for potentially serious condition, forcing follow-up question.")
                                clarifying_question = get_clarifying_question(response_text)
                                return {
                                    "is_question": True,
                                    "is_assessment": False,
                                    "possible_conditions": clarifying_question,
                                    "requires_upgrade": False
                                }
                
                # CRITICAL FIX: If confidence is below threshold, force a follow-up question
                if confidence < MIN_CONFIDENCE_THRESHOLD:
                    logger.info(f"Confidence too low ({confidence}%), forcing follow-up question.")
                    clarifying_question = get_clarifying_question(response_text)
                    return {
                        "is_question": True,
                        "is_assessment": False,
                        "possible_conditions": clarifying_question,
                        "requires_upgrade": False
                    }
                
                # SIMPLIFIED: Check for common conditions that should be MILD
                if "assessment" in assessment_data and "conditions" in assessment_data["assessment"]:
                    conditions = assessment_data["assessment"]["conditions"]
                    if conditions and len(conditions) > 0:
                        primary_condition = conditions[0]
                        primary_condition_name = primary_condition["name"].lower()
                        
                        # Check for common mild conditions
                        if any(condition in primary_condition_name for condition in COMMON_CONDITIONS_NO_UPGRADE):
                            assessment_data["assessment"]["triage_level"] = "MILD"
                            assessment_data["assessment"]["care_recommendation"] = "This can likely be managed at home."
                            logger.info(f"Set triage to MILD for common condition: {primary_condition_name}")
                
                # Check if confidence is high enough
                is_confident = confidence is not None and confidence >= MIN_CONFIDENCE_THRESHOLD
                logger.info(f"Confidence: {confidence}, Is confident: {is_confident}")
                
                # If emergency detected, ensure triage level is set to SEVERE
                if is_emergency and "assessment" in assessment_data:
                    assessment_data["assessment"]["triage_level"] = "SEVERE"
                    assessment_data["assessment"]["care_recommendation"] = "Seek immediate medical attention."
                    logger.info("Set triage level to SEVERE due to emergency detection")
                
                # Enforce paywall if necessary AND confidence is high enough
                requires_upgrade = False
                triage_level = assessment_data["assessment"].get("triage_level", "").upper() if "assessment" in assessment_data else ""
                care_recommendation = assessment_data["assessment"].get("care_recommendation", "").lower() if "assessment" in assessment_data else ""
                
                # Extract condition name for checking if it's a common/mild condition
                condition_name = ""
                if "assessment" in assessment_data and "conditions" in assessment_data["assessment"]:
                    if assessment_data["assessment"]["conditions"] and len(assessment_data["assessment"]["conditions"]) > 0:
                        condition_name = assessment_data["assessment"]["conditions"][0].get("name", "").lower()

                logger.info(f"Triage level: {triage_level}")
                logger.info(f"Care recommendation: {care_recommendation}")
                logger.info(f"Condition name: {condition_name}")

                # SIMPLIFIED: Only require upgrade if confidence is high enough AND it's not a common condition
                if is_confident and triage_level in ['MODERATE', 'SEVERE']:
                    # Check if it's a common condition that shouldn't require upgrade
                    is_common_condition = any(common_cond in condition_name for common_cond in COMMON_CONDITIONS_NO_UPGRADE)
                    
                    if not is_common_condition and user and hasattr(user, 'subscription_tier') and user.subscription_tier == UserTierEnum.FREE:
                        logger.info("FREE tier user needs upgrade for medical recommendation")
                        requires_upgrade = True
                        logger.info("Free user can see condition names but needs upgrade for detailed insights")
                    else:
                        if is_common_condition:
                            logger.info(f"Not requiring upgrade because '{condition_name}' is a common condition")
                        else:
                            logger.info(f"User has appropriate subscription tier or is not authenticated")
                else:
                    if not is_confident:
                        logger.info(f"Not requiring upgrade due to low confidence in assessment ({confidence})")
                    else:
                        logger.info(f"Not requiring upgrade as triage level is {triage_level}")
                
                assessment_data["requires_upgrade"] = requires_upgrade
                # Ensure confidence is always included in the response
                assessment_data["confidence"] = confidence
                logger.info(f"Setting requires_upgrade={requires_upgrade}")
                
                # Add condition name to the response for display in MessageItem.jsx
                if "assessment" in assessment_data and "conditions" in assessment_data["assessment"]:
                    if assessment_data["assessment"]["conditions"] and len(assessment_data["assessment"]["conditions"]) > 0:
                        assessment_data["conditionName"] = assessment_data["assessment"]["conditions"][0].get("name", "")
                
                return assessment_data
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
    else:
        logger.info("No JSON format detected in response")
    
    # If JSON extraction failed, determine question vs assessment
    is_question = "?" in response_text
    requires_upgrade = False
    
    # Check if this appears to be an assessment with care recommendations
    if not is_question and (is_emergency or needs_medical_attention):
        logger.info("Non-JSON response contains medical recommendation")
        
        # Try to estimate confidence from text
        if "high confidence" in response_text.lower():
            confidence = 90
        elif "moderate confidence" in response_text.lower():
            confidence = 80
        elif "low confidence" in response_text.lower():
            confidence = 60
        # else: confidence remains at DEFAULT_CONFIDENCE set at the beginning
        
        # Check for potentially serious conditions
        requires_differentiation = any(serious_cond in response_text.lower() for serious_cond in SERIOUS_CONDITIONS_REQUIRING_DIFFERENTIATION)
        if requires_differentiation or confidence < 95:  # Even stricter for serious conditions
            logger.info(f"Detected potentially serious condition requiring differentiation with confidence {confidence}%, forcing follow-up question.")
            clarifying_question = get_clarifying_question(response_text)
            return {
                "is_question": True,
                "is_assessment": False,
                "possible_conditions": clarifying_question,
                "requires_upgrade": False
            }
        
        # CRITICAL FIX: If confidence is below threshold, force a follow-up question
        if confidence < MIN_CONFIDENCE_THRESHOLD:
            logger.info(f"Confidence too low ({confidence}%), forcing follow-up question.")
            clarifying_question = get_clarifying_question(response_text)
            return {
                "is_question": True,
                "is_assessment": False,
                "possible_conditions": clarifying_question,
                "requires_upgrade": False
            }
        
        # SIMPLIFIED: Check for common conditions in the text
        is_common_condition = any(condition in response_text.lower() for condition in COMMON_CONDITIONS_NO_UPGRADE)
        
        # Only require upgrade if confidence is high enough AND it's not a common condition
        is_confident = confidence >= MIN_CONFIDENCE_THRESHOLD
        
        if is_confident and not is_common_condition and user and hasattr(user, 'subscription_tier') and user.subscription_tier == UserTierEnum.FREE:
            logger.info("FREE tier user needs upgrade for medical recommendation in text response")
            requires_upgrade = True
        elif not is_confident:
            logger.info(f"Not requiring upgrade due to low confidence in text response ({confidence})")
        elif is_common_condition:
            logger.info("Not requiring upgrade as this appears to be a common condition")
    
    # If the response contains uncertainty phrases, force a clarifying question
    if has_uncertainty or confidence < MIN_CONFIDENCE_THRESHOLD:
        logger.info("Detected uncertainty in non-question response, forcing clarifying question")
        clarifying_question = get_clarifying_question(response_text)
        return {
            "is_question": True,
            "is_assessment": False,
            "possible_conditions": clarifying_question,
            "requires_upgrade": False
        }
    
    logger.info(f"Final determination: is_question={is_question}, requires_upgrade={requires_upgrade}")
    
    # SIMPLIFIED: Determine triage level based on content and common conditions
    triage_level = "MILD"
    
    # Check for common conditions in the text
    is_common_condition = any(condition in response_text.lower() for condition in COMMON_CONDITIONS_NO_UPGRADE)
    
    if is_emergency:
        triage_level = "SEVERE"
        logger.info(f"Setting triage to SEVERE due to emergency phrases")
    elif requires_upgrade or (needs_medical_attention and not is_common_condition):
        triage_level = "MODERATE"
    elif is_common_condition:
        triage_level = "MILD"
        logger.info(f"Setting triage to MILD due to common condition detection")
    
    # Try to extract condition name from text for non-JSON responses
    # Look for medical terms followed by common terms in parentheses
    condition_name = None
    parentheses_pattern = r'([A-Za-z\s]+)\s*\(([A-Za-z\s]+)\)'
    matches = re.search(parentheses_pattern, response_text)
    if matches:
        medical_term = matches.group(1).strip()
        common_term = matches.group(2).strip()
        logger.info(f"Found medical term with common name: {medical_term} ({common_term})")
        condition_name = f"{medical_term} ({common_term})"
    
    return {
        "is_question": is_question,
        "is_assessment": not is_question,
        "possible_conditions": response_text,
        "triage_level": triage_level,
        "requires_upgrade": requires_upgrade,
        "confidence": confidence,  # Always include confidence in the response
        "conditionName": condition_name if not is_question else None  # Add condition name for display
    }