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
MIN_CONFIDENCE_THRESHOLD = 85  # Minimum confidence required for upgrade prompts - match frontend threshold

# Lists for condition severity validation
MILD_CONDITION_PHRASES = [
    "common cold", "seasonal allergy", "mild", "minor", "viral infection",
    "common nasal", "seasonal", "tension headache", "simple", "routine",
    "non-serious", "benign", "uncomplicated", "self-limiting", "transient"
]

SEVERE_CONDITION_PHRASES = [
    "heart attack", "stroke", "severe", "emergency", "critical", "urgent",
    "life-threatening", "dangerous", "acute", "serious", "immediate attention",
    "anaphylaxis", "pulmonary embolism", "meningitis", "appendicitis", "sepsis"
]

EMERGENCY_RECOMMENDATION_PHRASES = [
    "emergency", "immediate", "urgent", "911", "call ambulance", 
    "seek immediate", "go to hospital", "emergency room", "er", "call 911"
]

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

    # ✅ Check for emergency recommendations
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
    
    is_emergency = any(phrase in response_text.lower() for phrase in emergency_phrases)
    needs_medical_attention = any(phrase in response_text.lower() for phrase in medical_consultation_phrases)
    
    if is_emergency:
        logger.info("EMERGENCY recommendation detected in response")
    if needs_medical_attention:
        logger.info("Medical consultation recommendation detected in response")

    # ✅ Extract JSON-formatted response if present
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
                
                # ✅ Get confidence level
                if "assessment" in assessment_data and "conditions" in assessment_data["assessment"]:
                    conditions = assessment_data["assessment"]["conditions"]
                    if conditions and len(conditions) > 0:
                        confidence = conditions[0].get("confidence", DEFAULT_CONFIDENCE)
                
                # ✅ NEW: Validate and correct triage level and care recommendation
                if "assessment" in assessment_data and "conditions" in assessment_data["assessment"]:
                    conditions = assessment_data["assessment"]["conditions"]
                    if conditions and len(conditions) > 0:
                        primary_condition = conditions[0]
                        primary_condition_name = primary_condition["name"].lower()
                        primary_confidence = primary_condition.get("confidence", DEFAULT_CONFIDENCE)
                        
                        triage_level = assessment_data["assessment"].get("triage_level", "MODERATE")
                        care_recommendation = assessment_data["assessment"].get("care_recommendation", "")
                        
                        # Store original values for logging
                        original_triage = triage_level
                        original_recommendation = care_recommendation
                        
                        # Check for mismatches between condition severity and recommendations
                        is_mild_condition = any(phrase in primary_condition_name for phrase in MILD_CONDITION_PHRASES)
                        is_severe_condition = any(phrase in primary_condition_name for phrase in SEVERE_CONDITION_PHRASES)
                        is_emergency_recommendation = any(phrase in care_recommendation.lower() for phrase in EMERGENCY_RECOMMENDATION_PHRASES)
                        
                        correction_made = False
                        
                        # Case 1: Mild condition with emergency recommendation
                        if is_mild_condition and is_emergency_recommendation:
                            logger.warning(
                                f"CORRECTING: Mild condition '{primary_condition['name']}' "
                                f"incorrectly marked with emergency recommendation. "
                                f"Original triage={original_triage}, Original recommendation='{original_recommendation[:30]}...'"
                            )
                            assessment_data["assessment"]["triage_level"] = "MILD"
                            assessment_data["assessment"]["care_recommendation"] = "This can likely be managed at home."
                            correction_made = True
                        
                        # Case 2: Severe condition without emergency recommendation
                        # 🚨 FIX: Only upgrade to emergency if confidence is high enough
                        elif is_severe_condition and not is_emergency_recommendation and triage_level != "SEVERE":
                            if primary_confidence >= MIN_CONFIDENCE_THRESHOLD:
                                logger.warning(
                                    f"CORRECTING: Severe condition '{primary_condition['name']}' "
                                    f"missing emergency recommendation. "
                                    f"Confidence={primary_confidence}% -> Applying SEVERE triage. "
                                    f"Original triage={original_triage}, Original recommendation='{original_recommendation[:30]}...'"
                                )
                                assessment_data["assessment"]["triage_level"] = "SEVERE"
                                assessment_data["assessment"]["care_recommendation"] = "Seek immediate medical attention."
                                correction_made = True
                            else:
                                logger.info(
                                    f"NOT changing recommendation: '{primary_condition['name']}' "
                                    f"has LOW confidence ({primary_confidence}%) - keeping original triage={original_triage}"
                                )
                        
                        # Case 3: Triage level says MILD but recommendation suggests emergency
                        elif triage_level == "MILD" and is_emergency_recommendation:
                            logger.warning(
                                f"CORRECTING: Triage level MILD conflicts with emergency recommendation. "
                                f"Condition='{primary_condition['name']}', Confidence={primary_confidence}%"
                            )
                            # Decide based on condition name and confidence
                            if is_severe_condition and primary_confidence >= MIN_CONFIDENCE_THRESHOLD:
                                assessment_data["assessment"]["triage_level"] = "SEVERE"
                                logger.info(f"Changed triage to SEVERE based on condition name and high confidence")
                            else:
                                # Keep it MILD and fix the recommendation
                                assessment_data["assessment"]["care_recommendation"] = "This can likely be managed at home."
                                logger.info(f"Kept MILD triage but fixed recommendation to match")
                            correction_made = True
                        
                        # Case 4: Triage level says SEVERE but recommendation doesn't suggest emergency
                        elif triage_level == "SEVERE" and not is_emergency_recommendation:
                            # Only enforce emergency recommendation if confidence is high enough
                            if primary_confidence >= MIN_CONFIDENCE_THRESHOLD:
                                logger.warning(
                                    f"CORRECTING: Triage level SEVERE without emergency recommendation. "
                                    f"Condition='{primary_condition['name']}', Confidence={primary_confidence}% "
                                    f"-> Adding emergency recommendation"
                                )
                                assessment_data["assessment"]["care_recommendation"] = "Seek immediate medical attention."
                                correction_made = True
                            else:
                                # Downgrade triage level for low confidence cases
                                logger.warning(
                                    f"CORRECTING: Downgrading SEVERE triage due to low confidence ({primary_confidence}%). "
                                    f"Condition='{primary_condition['name']}' -> Changing to MODERATE"
                                )
                                assessment_data["assessment"]["triage_level"] = "MODERATE"
                                assessment_data["assessment"]["care_recommendation"] = "Consider consulting with a healthcare professional."
                                correction_made = True
                        
                        # Log any corrections made
                        if correction_made and not is_production:
                            logger.info(f"Corrected assessment: Condition='{primary_condition['name']}', " +
                                        f"Original triage={original_triage}, New triage={assessment_data['assessment']['triage_level']}, " +
                                        f"Original recommendation='{original_recommendation[:30]}...', " +
                                        f"New recommendation='{assessment_data['assessment']['care_recommendation'][:30]}...', " +
                                        f"Confidence={primary_confidence}")
                
                # ✅ Check if confidence is high enough
                is_confident = confidence is not None and confidence >= MIN_CONFIDENCE_THRESHOLD
                logger.info(f"Confidence: {confidence}, Is confident: {is_confident}")
                
                # ✅ If emergency detected, ensure triage level is set to SEVERE
                # 🚨 FIX: Only enforce SEVERE if confidence is high enough
                if is_emergency and "assessment" in assessment_data:
                    if confidence >= MIN_CONFIDENCE_THRESHOLD:
                        assessment_data["assessment"]["triage_level"] = "SEVERE"
                        assessment_data["assessment"]["care_recommendation"] = "Seek immediate medical attention."
                        logger.info("Set triage level to SEVERE due to emergency detection (high confidence)")
                    else:
                        # For low confidence, use MODERATE instead
                        assessment_data["assessment"]["triage_level"] = "MODERATE"
                        assessment_data["assessment"]["care_recommendation"] = "Consider consulting with a healthcare professional."
                        logger.info(f"Using MODERATE triage due to low confidence ({confidence}%) despite emergency phrases")
                
                # ✅ Enforce paywall if necessary AND confidence is high enough
                requires_upgrade = False
                triage_level = assessment_data["assessment"].get("triage_level", "").upper() if "assessment" in assessment_data else ""
                care_recommendation = assessment_data["assessment"].get("care_recommendation", "").lower() if "assessment" in assessment_data else ""

                logger.info(f"Triage level: {triage_level}")
                logger.info(f"Care recommendation: {care_recommendation}")

                if is_confident and (triage_level in ['MODERATE', 'SEVERE'] or 
                    'doctor' in care_recommendation or 
                    'medical attention' in care_recommendation or
                    'urgent care' in care_recommendation or
                    'emergency' in care_recommendation or
                    is_emergency or 
                    needs_medical_attention):
                    
                    logger.info("Response contains medical recommendation with high confidence that may require upgrade")
                    
                    # ✅ Check user's subscription tier
                    if user and hasattr(user, 'subscription_tier') and user.subscription_tier == UserTierEnum.FREE:
                        logger.info("FREE tier user needs upgrade for medical recommendation")
                        requires_upgrade = True
                        # FIXED: Don't hide condition names for free users
                        # Instead, just mark that an upgrade is required to see more details
                        logger.info("Free user can see condition names but needs upgrade for detailed insights")
                    else:
                        logger.info("User has appropriate subscription tier or is not authenticated")
                else:
                    if not is_confident:
                        logger.info(f"Not requiring upgrade due to low confidence in assessment ({confidence})")
                    else:
                        logger.info("Not requiring upgrade as no medical recommendation detected")
                
                assessment_data["requires_upgrade"] = requires_upgrade
                # Ensure confidence is always included in the response
                assessment_data["confidence"] = confidence
                logger.info(f"Setting requires_upgrade={requires_upgrade}")
                return assessment_data
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
    else:
        logger.info("No JSON format detected in response")
    
    # ✅ If JSON extraction failed, determine question vs assessment
    is_question = "?" in response_text
    requires_upgrade = False
    
    # Check if this appears to be an assessment with care recommendations
    if not is_question and (is_emergency or needs_medical_attention):
        logger.info("Non-JSON response contains medical recommendation")
        
        # ✅ NEW: Try to estimate confidence from text
        if "high confidence" in response_text.lower():
            confidence = 90
        elif "moderate confidence" in response_text.lower():
            confidence = 80
        elif "low confidence" in response_text.lower():
            confidence = 60
        # else: confidence remains at DEFAULT_CONFIDENCE set at the beginning
        
        # ✅ Only require upgrade if confidence is high enough
        is_confident = confidence >= MIN_CONFIDENCE_THRESHOLD
        
        # Check user's subscription tier
        if is_confident and user and hasattr(user, 'subscription_tier') and user.subscription_tier == UserTierEnum.FREE:
            logger.info("FREE tier user needs upgrade for medical recommendation in text response")
            requires_upgrade = True
        elif not is_confident:
            logger.info(f"Not requiring upgrade due to low confidence in text response ({confidence})")
    
    logger.info(f"Final determination: is_question={is_question}, requires_upgrade={requires_upgrade}")
    
    # 🚨 FIX: Only set triage level to SEVERE if confidence is high enough
    triage_level = "MILD"
    if is_emergency:
        if confidence >= MIN_CONFIDENCE_THRESHOLD:
            triage_level = "SEVERE"
            logger.info(f"Setting triage to SEVERE due to emergency phrases with confidence {confidence}%")
        else:
            triage_level = "MODERATE"
            logger.info(f"Setting triage to MODERATE despite emergency phrases due to low confidence {confidence}%")
    elif requires_upgrade or needs_medical_attention:
        triage_level = "MODERATE"
    
    return {
        "is_question": is_question,
        "is_assessment": not is_question,
        "possible_conditions": response_text,
        "triage_level": triage_level,
        "requires_upgrade": requires_upgrade,
        "confidence": confidence  # Always include confidence in the response
    }