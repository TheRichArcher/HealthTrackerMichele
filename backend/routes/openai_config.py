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
    "non-serious", "benign", "uncomplicated", "self-limiting", "transient",
    "sunburn"  # Explicitly add sunburn
]

# Common conditions that shouldn't trigger upgrade prompts even with doctor recommendations
COMMON_CONDITIONS_NO_UPGRADE = [
    "common cold", "seasonal allergy", "mild headache", "tension headache",
    "sinus infection", "sinusitis", "rhinitis", "sore throat", "pharyngitis",
    "gastroenteritis", "stomach flu", "diarrhea", "constipation",
    "urinary tract infection", "uti", "conjunctivitis", "pink eye",
    "dermatitis", "eczema", "contact dermatitis", "insomnia",
    "mild anxiety", "mild depression", "muscle strain", "sprain",
    "plantar fasciitis", "heel pain", "achilles tendinitis",
    "mild dehydration", "indigestion", "heartburn", "acid reflux",
    "sunburn"  # Explicitly add sunburn
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
      {"name": "Condition Name", "confidence": 70},
      {"name": "Alternative Condition", "confidence": 20}
    ],
    "triage_level": "MILD|MODERATE|SEVERE",
    "care_recommendation": "Brief recommendation based on triage level",
    "disclaimer": "This assessment is for informational purposes only and does not replace professional medical advice."
  }
}
</json>
"""

def extract_real_condition_name(response_text, placeholder_name):
    """
    Extract a real condition name from the response text when a placeholder like 'Condition 1' is detected.
    """
    logger.info(f"Attempting to extract real condition name to replace '{placeholder_name}'")
    
    # Look for phrases that might indicate a condition name
    condition_patterns = [
        r"most likely (?:condition|diagnosis) is ([^\.]+)",
        r"likely (?:suffering from|experiencing|have|has) ([^\.]+)",
        r"symptoms suggest ([^\.]+)",
        r"consistent with ([^\.]+)",
        r"indicative of ([^\.]+)",
        r"appears to be ([^\.]+)",
        r"points to ([^\.]+)",
        r"diagnosed with ([^\.]+)"
    ]
    
    # Try each pattern to find a condition name
    for pattern in condition_patterns:
        matches = re.search(pattern, response_text, re.IGNORECASE)
        if matches:
            extracted_name = matches.group(1).strip()
            # Clean up the extracted name
            extracted_name = re.sub(r'[,\.]$', '', extracted_name)  # Remove trailing commas or periods
            
            # Don't return if it's just another placeholder
            if re.match(r'^condition\s+\d+$', extracted_name, re.IGNORECASE):
                continue
                
            logger.info(f"Extracted condition name: '{extracted_name}' using pattern: '{pattern}'")
            return extracted_name
    
    # If no specific pattern matches, try to find medical condition names
    common_conditions = [
        "Migraine", "Common Cold", "Influenza", "Gastroenteritis", 
        "Sinusitis", "Allergic Rhinitis", "Bronchitis", "Conjunctivitis",
        "Urinary Tract Infection", "Dermatitis", "Anxiety", "Depression",
        "Hypertension", "Diabetes", "Asthma", "Arthritis", "Pneumonia",
        "Gastroesophageal Reflux Disease", "Irritable Bowel Syndrome",
        "Plantar Fasciitis", "Achilles Tendinitis", "Herpes Zoster", "Shingles",
        "Dehydration", "Heat Exhaustion", "Insomnia", "Tension Headache",
        "Sunburn"  # Explicitly add Sunburn
    ]
    
    for condition in common_conditions:
        if condition.lower() in response_text.lower():
            logger.info(f"Found condition name '{condition}' in response text")
            return condition
    
    # If all else fails, return a generic but more informative name
    logger.warning(f"Could not extract specific condition name to replace '{placeholder_name}'")
    return "Medical Condition"

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
    
    is_emergency = any(phrase in response_text.lower() for phrase in emergency_phrases)
    needs_medical_attention = any(phrase in response_text.lower() for phrase in medical_consultation_phrases)
    
    if is_emergency:
        logger.info("EMERGENCY recommendation detected in response")
    if needs_medical_attention:
        logger.info("Medical consultation recommendation detected in response")

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
                        
                        # Check if the condition name is a generic placeholder like "Condition 1"
                        if re.match(r'^condition\s+\d+$', conditions[0]["name"], re.IGNORECASE):
                            logger.warning(f"Detected generic placeholder condition name: '{conditions[0]['name']}'")
                            
                            # Try to extract a real condition name from the full response
                            real_condition_name = extract_real_condition_name(response_text, conditions[0]["name"])
                            
                            # Replace the placeholder with the extracted name
                            conditions[0]["name"] = real_condition_name
                            logger.info(f"Replaced placeholder with extracted condition name: '{real_condition_name}'")
                            
                            # Also add a common name if appropriate
                            common_name_map = {
                                # Respiratory conditions
                                "Migraine": "Severe Headache",
                                "Influenza": "Flu",
                                "Gastroenteritis": "Stomach Flu",
                                "Sinusitis": "Sinus Infection",
                                "Allergic Rhinitis": "Hay Fever",
                                "Bronchitis": "Chest Cold",
                                "Conjunctivitis": "Pink Eye",
                                "Urinary Tract Infection": "UTI",
                                "Dermatitis": "Skin Rash",
                                "Gastroesophageal Reflux Disease": "Acid Reflux",
                                "Herpes Zoster": "Shingles",
                                "Plantar Fasciitis": "Heel Pain",
                                "Achilles Tendinitis": "Ankle Pain",
                                "Pharyngitis": "Sore Throat",
                                "Otitis Media": "Middle Ear Infection",
                                "Otitis Externa": "Swimmer's Ear",
                                "Rhinitis": "Runny Nose",
                                "Cephalgia": "Headache",
                                "Tension Cephalgia": "Tension Headache",
                                "Cluster Cephalgia": "Cluster Headache",
                                "Hypertension": "High Blood Pressure",
                                "Hyperlipidemia": "High Cholesterol",
                                "Diabetes Mellitus": "Diabetes",
                                "Insomnia": "Sleep Disorder",
                                "Anxiety Disorder": "Anxiety",
                                "Major Depressive Disorder": "Depression",
                                "Cellulitis": "Skin Infection",
                                "Tinea Pedis": "Athlete's Foot",
                                "Tinea Corporis": "Ringworm",
                                "Tinea Cruris": "Jock Itch",
                                "Onychomycosis": "Fungal Nail Infection",
                                "Acne Vulgaris": "Acne",
                                "Seborrheic Dermatitis": "Dandruff",
                                "Rosacea": "Facial Redness",
                                "Psoriasis": "Scaly Skin Patches",
                                "Urticaria": "Hives",
                                "Dyspepsia": "Indigestion",
                                "Constipation": "Constipation",
                                "Diarrhea": "Diarrhea",
                                "Hemorrhoids": "Piles",
                                "Dysmenorrhea": "Menstrual Cramps",
                                "Premenstrual Syndrome": "PMS",
                                "Cystitis": "Bladder Infection",
                                "Nephrolithiasis": "Kidney Stones",
                                "Epicondylitis": "Tennis Elbow",
                                "Carpal Tunnel Syndrome": "Wrist Pain",
                                "Tendinitis": "Tendon Inflammation",
                                "Bursitis": "Joint Inflammation",
                                "Osteoarthritis": "Joint Pain",
                                "Myalgia": "Muscle Pain",
                                "Coryza": "Common Cold",
                                "Upper Respiratory Infection": "Common Cold",
                                "Acute Bronchitis": "Chest Cold",
                                "Pneumonia": "Lung Infection",
                                "Tonsillitis": "Tonsil Infection",
                                "Laryngitis": "Voice Box Inflammation",
                                "Dehydration": "Dehydration",
                                "Sunburn": "Sunburn"  # Add sunburn explicitly
                            }
                            
                            if real_condition_name in common_name_map:
                                conditions[0]["common_name"] = common_name_map[real_condition_name]
                                logger.info(f"Added common name: '{conditions[0]['common_name']}'")
                
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
                    
                    # Also check if the recommendation is just a standard "see doctor if symptoms persist"
                    is_standard_recommendation = "if symptoms persist" in care_recommendation or \
                                               "if it doesn't improve" in care_recommendation
                    
                    if not is_common_condition and not (is_standard_recommendation and triage_level == 'MODERATE'):
                        logger.info("Response contains medical recommendation with high confidence that may require upgrade")
                        
                        # Check user's subscription tier
                        if user and hasattr(user, 'subscription_tier') and user.subscription_tier == UserTierEnum.FREE:
                            logger.info("FREE tier user needs upgrade for medical recommendation")
                            requires_upgrade = True
                            logger.info("Free user can see condition names but needs upgrade for detailed insights")
                        else:
                            logger.info("User has appropriate subscription tier or is not authenticated")
                    else:
                        if is_common_condition:
                            logger.info(f"Not requiring upgrade because '{condition_name}' is a common condition")
                        else:
                            logger.info(f"Not requiring upgrade because recommendation is standard advice")
                else:
                    if not is_confident:
                        logger.info(f"Not requiring upgrade due to low confidence in assessment ({confidence})")
                    else:
                        logger.info(f"Not requiring upgrade as triage level is {triage_level}")
                
                assessment_data["requires_upgrade"] = requires_upgrade
                # Ensure confidence is always included in the response
                assessment_data["confidence"] = confidence
                logger.info(f"Setting requires_upgrade={requires_upgrade}")
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
    
    return {
        "is_question": is_question,
        "is_assessment": not is_question,
        "possible_conditions": response_text,
        "triage_level": triage_level,
        "requires_upgrade": requires_upgrade,
        "confidence": confidence  # Always include confidence in the response
    }