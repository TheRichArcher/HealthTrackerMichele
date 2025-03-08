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
MIN_CONFIDENCE_THRESHOLD = 85  # Reduced from 90% to 85% for more flexibility
QUESTION_COUNT_THRESHOLD = 5  # Reduced from 8 to 5 to align with simplified prompt

# Lists for condition severity validation - keeping these minimal
MILD_CONDITION_PHRASES = [
    "common cold", "seasonal allergy", "mild", "minor", "viral infection",
    "sunburn"  # Explicitly add sunburn
]

# Common conditions that shouldn't trigger upgrade prompts even with doctor recommendations
COMMON_CONDITIONS_NO_UPGRADE = [
    "common cold", "seasonal allergy", "mild headache", "tension headache",
    "sinus infection", "sinusitis", "sore throat", 
    "stomach flu", "diarrhea", "constipation",
    "urinary tract infection", "uti", "pink eye",
    "sunburn", "acid reflux", "gerd"  # Added acid reflux/GERD as common conditions
]

# Potentially serious conditions that require more thorough questioning
SERIOUS_CONDITIONS_REQUIRING_DIFFERENTIATION = [
    "heat exhaustion", "heat stroke", "dehydration", "concussion", "migraine", 
    "meningitis", "stroke", "heart attack", "pulmonary embolism", "sepsis",
    "diabetic ketoacidosis", "anaphylaxis", "appendicitis", "chest pain",
    "angina", "myocardial infarction", "pneumonia", "pneumothorax"
]

# Conditions that require checking for recurring/chronic patterns
CHRONIC_CONDITIONS_REQUIRING_HISTORY = [
    "ibs", "irritable bowel syndrome", "gerd", "acid reflux", "gastroesophageal reflux",
    "migraine", "tension headache", "cluster headache", "chronic fatigue",
    "fibromyalgia", "arthritis", "asthma", "eczema", "psoriasis"
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
        "Do you have a history of heart problems or high blood pressure?",
        "Have you tried any medications like antacids, and if so, did they help?",
        "Do you ever experience a sour or bitter taste in your mouth, especially after meals or when lying down?",
        "How long have you been experiencing these symptoms?"
    ],
    "digestive": [
        "How long have you been experiencing these symptoms?",
        "Have you tried any medications like antacids, and if so, did they help?",
        "Do you ever experience a sour or bitter taste in your mouth, especially after meals or when lying down?",
        "Have you noticed any changes in your bowel movements?",
        "Do you have any known food allergies or intolerances?",
        "Have you had these symptoms multiple times in the past few months?",
        "Do these symptoms tend to occur after eating certain foods?"
    ],
    "neurological": [
        "Did your symptoms come on suddenly or gradually?",
        "Have you experienced these symptoms before?",
        "On a scale of 1-10, how severe is your headache?",
        "Do you have any sensitivity to light or sound?",
        "Have you had these symptoms multiple times in the past few months?",
        "Do you have any family history of migraines or neurological conditions?",
        "Are you experiencing any weakness or numbness on one side of your body?"
    ],
    "stroke_vs_migraine": [
        "Did your symptoms appear suddenly (within seconds or minutes) or develop gradually (over 30+ minutes)?",
        "Do you have any weakness or numbness on one side of your body?",
        "Are you experiencing any difficulty speaking or understanding speech?",
        "Have you had similar headaches or symptoms in the past?",
        "Do you have any known risk factors for stroke such as high blood pressure, diabetes, or smoking?",
        "Is this the worst headache of your life or similar to previous headaches you've had?"
    ],
    "chronic_condition_check": [
        "Have you experienced these symptoms multiple times in the past few months?",
        "How frequently do these symptoms occur?",
        "Have you noticed any patterns or triggers for these symptoms?",
        "Have you been diagnosed with any chronic conditions in the past?",
        "Do these symptoms interfere with your daily activities?"
    ],
    "uncertain": [
        "I understand you're not sure, but this is important for your safety. Could you try to describe any other symptoms you've noticed?",
        "When you say you're not sure, is it because you haven't checked, or because the symptom is unclear?",
        "For your safety, I need to rule out serious conditions. Have you experienced any severe symptoms like extreme confusion, fainting, or severe pain?"
    ]
}

# Simplified system prompt to align with symptom_routes.py
SYSTEM_PROMPT = """You are Michele, an AI medical assistant trained to have conversations like a doctor's visit.
Your goal is to understand the user's symptoms through a conversation before providing any potential diagnosis.

CRITICAL INSTRUCTIONS:
1. ALWAYS return a valid JSON response with:
   - "is_assessment": boolean (true if ≥85% confidence diagnosis)
   - "is_question": boolean (true if asking a follow-up question)
   - "possible_conditions": string (question or assessment text)
   - "confidence": number (0-100)
   - "triage_level": string ("MILD", "MODERATE", "SEVERE")
   - "care_recommendation": string (brief advice)

2. For assessments (is_assessment=true), include:
   - "assessment": {"conditions": [{"name": "Medical Term (Common Name)", "confidence": number, "is_chronic": boolean}], "triage_level": string, "care_recommendation": string}

3. Ask at least 5 questions before providing a diagnosis.
4. Avoid diagnosis if confidence <85%.
5. Use 'Medical Term (Common Name)' for conditions.
6. For potentially serious conditions, ask additional questions to differentiate.
7. If unsure, ask clarifying questions instead of guessing.
"""

def create_default_response(symptom: str = "", conversation_history: list = None) -> Dict:
    """
    Provides a default structured response when AI fails to process input.
    Includes a user-friendly message encouraging more details.
    """
    logger.info("Returning default response due to empty or invalid AI response")
    if conversation_history:
        logger.debug(f"Conversation history leading to default response: {json.dumps(conversation_history)}")
    if symptom:
        logger.debug(f"Symptom leading to default response: {symptom}")
    
    return {
        "is_assessment": False,
        "is_question": True,
        "possible_conditions": "I'm sorry, I couldn't process that response. Could you please provide more details about your symptoms?",
        "confidence": None,
        "triage_level": None,
        "care_recommendation": None,
        "requires_upgrade": False,
        "disclaimer": "This assessment is for informational purposes only and does not replace professional medical advice."
    }

def get_clarifying_question(response_text: str, conversation_history=None) -> str:
    """
    Returns an appropriate clarifying question based on the context of the conversation.
    """
    # Check for stroke vs migraine context
    if any(term in response_text.lower() for term in ["stroke", "migraine", "headache", "head", "neurological", "vision", "speech", "weakness"]):
        questions = CLARIFYING_QUESTIONS["stroke_vs_migraine"]
    # Check for heat-related or dehydration context
    elif any(term in response_text.lower() for term in ["heat", "hot", "dehydrat", "dizz", "faint", "weak", "sweat"]):
        questions = CLARIFYING_QUESTIONS["dehydration_heat"]
    # Check for head injury context
    elif any(term in response_text.lower() for term in ["head", "concuss", "hit", "fall", "dizz", "nause", "vomit"]):
        questions = CLARIFYING_QUESTIONS["head_injury"]
    # Check for chest pain context
    elif any(term in response_text.lower() for term in ["chest", "heart", "pain", "breath", "pressure", "burn"]):
        questions = CLARIFYING_QUESTIONS["chest_pain"]
    # Check for digestive issues
    elif any(term in response_text.lower() for term in ["stomach", "digest", "acid", "reflux", "gerd", "nausea", "vomit", "food", "bowel", "ibs"]):
        # Check if we need to ask about recurring symptoms
        if conversation_history and not any("multiple times" in msg.get("message", "").lower() for msg in conversation_history if msg.get("isBot", False)):
            return "Have you experienced these symptoms multiple times in the past few months?"
        questions = CLARIFYING_QUESTIONS["digestive"]
    # Check for neurological issues
    elif any(term in response_text.lower() for term in ["headache", "migraine", "dizz", "vertigo", "neurological", "vision", "aura"]):
        # Check if we need to ask about recurring symptoms
        if conversation_history and not any("multiple times" in msg.get("message", "").lower() for msg in conversation_history if msg.get("isBot", False)):
            return "Have you experienced these headaches or neurological symptoms multiple times in the past few months?"
        questions = CLARIFYING_QUESTIONS["neurological"]
    # Check for potentially chronic conditions
    elif any(chronic_cond in response_text.lower() for chronic_cond in CHRONIC_CONDITIONS_REQUIRING_HISTORY):
        # Check if we need to ask about recurring symptoms
        if conversation_history and not any("multiple times" in msg.get("message", "").lower() for msg in conversation_history if msg.get("isBot", False)):
            return "Have you experienced these symptoms multiple times in the past few months?"
        questions = CLARIFYING_QUESTIONS["chronic_condition_check"]
    # Default to general uncertain questions
    else:
        questions = CLARIFYING_QUESTIONS["uncertain"]
    
    # Return a random question from the appropriate category
    import random
    return random.choice(questions)

def count_questions_in_conversation(conversation_history):
    """
    Count the number of questions asked by the bot in the conversation history.
    """
    if not conversation_history:
        return 0
    
    question_count = 0
    for msg in conversation_history:
        if msg.get("isBot", False) and "?" in msg.get("message", ""):
            question_count += 1
    
    return question_count

def check_chronic_condition_requirements(conversation_history, condition_name):
    """
    Simplified check for chronic conditions based on conversation history.
    """
    if not conversation_history:
        return False
    
    # Check if this is a condition that requires recurring symptom verification
    is_chronic_condition = any(chronic_cond in condition_name.lower() for chronic_cond in CHRONIC_CONDITIONS_REQUIRING_HISTORY)
    
    if not is_chronic_condition:
        return True  # Not a chronic condition, so no special requirements
    
    # Check if we've asked about recurring symptoms and received a positive response
    for i, msg in enumerate(conversation_history):
        if msg.get("isBot", False) and "multiple times" in msg.get("message", "").lower() and "?" in msg.get("message", ""):
            # Check if the user's next response was positive
            if i + 1 < len(conversation_history) and not conversation_history[i+1].get("isBot", True):
                user_response = conversation_history[i+1].get("message", "").lower()
                if any(pos in user_response for pos in ["yes", "yeah", "yep", "correct", "i do", "i have", "multiple", "recurring", "chronic", "often", "frequently"]):
                    return True
    
    return False

def check_stroke_vs_migraine_differentiation(conversation_history, condition_name):
    """
    Simplified check for stroke vs migraine differentiation.
    """
    if not conversation_history:
        return True  # No conversation history to check
    
    # Check if this is a stroke or migraine diagnosis
    is_stroke = "stroke" in condition_name.lower()
    is_migraine = "migraine" in condition_name.lower()
    
    if not (is_stroke or is_migraine):
        return True  # Not stroke or migraine, so no special requirements
    
    # Check for at least one key differentiation question
    for msg in conversation_history:
        if msg.get("isBot", False):
            bot_message = msg.get("message", "").lower()
            if ("sudden" in bot_message and "gradual" in bot_message) or ("weakness" in bot_message or "numbness" in bot_message) or ("previous" in bot_message or "before" in bot_message):
                return True
    
    return False

def clean_ai_response(response_text: str, user=None, conversation_history=None, symptom: str = "") -> Union[Dict, str]:
    """
    Processes the AI response and determines if it's a question or assessment.
    Now includes subscription tier and confidence threshold enforcement.
    Added symptom parameter for better logging.
    """
    # Log user information for debugging
    is_production = current_app.config.get("ENV") == "production" if current_app else False
    
    if user:
        logger.info(f"Processing response for user with tier: {user.subscription_tier if hasattr(user, 'subscription_tier') else 'Unknown'}")
    else:
        logger.info("Processing response for unauthenticated user (user object not provided)")
    
    # Log the inputs for debugging
    logger.debug(f"Symptom input: {symptom}")
    if conversation_history:
        logger.debug(f"Conversation history: {json.dumps(conversation_history)}")
    
    if not isinstance(response_text, str) or not response_text.strip():
        logger.warning("Invalid or empty response received from OpenAI")
        return create_default_response(symptom, conversation_history)
    
    logger.info(f"Processing AI response: {response_text[:100]}...")

    # Count questions asked so far
    question_count = count_questions_in_conversation(conversation_history) if conversation_history else 0
    logger.info(f"Questions asked so far: {question_count}")
    
    # If we haven't asked enough questions yet, force a follow-up question
    if question_count < QUESTION_COUNT_THRESHOLD and "?" not in response_text:
        logger.info(f"Not enough questions asked yet ({question_count}/{QUESTION_COUNT_THRESHOLD}), forcing follow-up question.")
        clarifying_question = get_clarifying_question(response_text, conversation_history)
        return {
            "is_question": True,
            "is_assessment": False,
            "possible_conditions": clarifying_question,
            "requires_upgrade": False
        }

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
                
                # Ensure is_assessment and is_question are set correctly
                if "assessment" in assessment_data:
                    assessment_data["is_assessment"] = True
                    assessment_data["is_question"] = False
                    logger.info("Found assessment JSON data, marking as assessment")
                else:
                    assessment_data["is_assessment"] = True
                    assessment_data["is_question"] = False
                
                # Get confidence level
                if "assessment" in assessment_data and "conditions" in assessment_data["assessment"]:
                    conditions = assessment_data["assessment"]["conditions"]
                    if conditions and len(conditions) > 0:
                        confidence = conditions[0].get("confidence", DEFAULT_CONFIDENCE)
                        condition_name = conditions[0].get("name", "").lower()
                        
                        # Check for stroke vs migraine differentiation
                        if ("stroke" in condition_name or "migraine" in condition_name) and not check_stroke_vs_migraine_differentiation(conversation_history, condition_name):
                            logger.info(f"Stroke vs migraine differentiation not properly performed for: {condition_name}")
                            clarifying_question = get_clarifying_question("stroke migraine", conversation_history)
                            return {
                                "is_question": True,
                                "is_assessment": False,
                                "possible_conditions": clarifying_question,
                                "requires_upgrade": False
                            }
                        
                        # Check for chronic condition requirements
                        if not check_chronic_condition_requirements(conversation_history, condition_name):
                            logger.info(f"Chronic condition requirements not met for: {condition_name}")
                            return {
                                "is_question": True,
                                "is_assessment": False,
                                "possible_conditions": "Have you experienced these symptoms multiple times in the past few months?",
                                "requires_upgrade": False
                            }
                
                # If confidence is below threshold, force a follow-up question
                if confidence < MIN_CONFIDENCE_THRESHOLD:
                    logger.info(f"Confidence too low ({confidence}%), forcing follow-up question.")
                    clarifying_question = get_clarifying_question(response_text, conversation_history)
                    return {
                        "is_question": True,
                        "is_assessment": False,
                        "possible_conditions": clarifying_question,
                        "requires_upgrade": False
                    }
                
                # Check for common conditions that should be MILD
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
                        
                        # Add is_chronic flag based on conversation history
                        is_chronic = False
                        if conversation_history:
                            for msg in conversation_history:
                                if not msg.get("isBot", True) and any(pos in msg.get("message", "").lower() for pos in ["yes", "yeah", "yep", "correct", "i do", "i have", "multiple", "recurring", "chronic", "often", "frequently"]):
                                    for prev_msg in conversation_history:
                                        if prev_msg.get("isBot", False) and "multiple times" in prev_msg.get("message", "").lower():
                                            is_chronic = True
                                            break
                        
                        # Add is_first_occurrence flag (opposite of is_chronic)
                        assessment_data["assessment"]["is_first_occurrence"] = not is_chronic
                        
                        # Add is_chronic flag to each condition
                        for condition in conditions:
                            condition["is_chronic"] = is_chronic
                
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

                # Only require upgrade if confidence is high enough AND it's not a common condition
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
                
                # Extract the text before the JSON for the visible response
                visible_text = response_text.split("<json>")[0].strip() if "<json>" in response_text else response_text
                assessment_data["possible_conditions"] = visible_text  # Use the text part for display
                
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
        
        # Check for chronic conditions without proper verification
        potential_chronic_condition = any(chronic_cond in response_text.lower() for chronic_cond in CHRONIC_CONDITIONS_REQUIRING_HISTORY)
        if potential_chronic_condition and conversation_history and not any("multiple times" in msg.get("message", "").lower() for msg in conversation_history if msg.get("isBot", False)):
            logger.info("Detected potential chronic condition without recurring symptom check, forcing clarifying question")
            return {
                "is_question": True,
                "is_assessment": False,
                "possible_conditions": "Have you experienced these symptoms multiple times in the past few months?",
                "requires_upgrade": False
            }
        
        # If confidence is below threshold, force a follow-up question
        if confidence < MIN_CONFIDENCE_THRESHOLD:
            logger.info(f"Confidence too low ({confidence}%), forcing follow-up question.")
            clarifying_question = get_clarifying_question(response_text, conversation_history)
            return {
                "is_question": True,
                "is_assessment": False,
                "possible_conditions": clarifying_question,
                "requires_upgrade": False
            }
        
        # Check for common conditions in the text
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
    if has_uncertainty and not is_question:
        logger.info("Detected uncertainty in non-question response, forcing clarifying question")
        clarifying_question = get_clarifying_question(response_text, conversation_history)
        return {
            "is_question": True,
            "is_assessment": False,
            "possible_conditions": clarifying_question,
            "requires_upgrade": False
        }
    
    logger.info(f"Final determination: is_question={is_question}, requires_upgrade={requires_upgrade}")
    
    # Determine triage level based on content and common conditions
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
    condition_name = None
    parentheses_pattern = r'([A-Za-z\s]+)\s*\(([A-Za-z\s]+)\)'
    matches = re.search(parentheses_pattern, response_text)
    if matches:
        medical_term = matches.group(1).strip()
        common_term = matches.group(2).strip()
        logger.info(f"Found medical term with common name: {medical_term} ({common_term})")
        condition_name = f"{medical_term} ({common_term})"
    
    # Determine if this is a first occurrence or chronic condition
    is_first_occurrence = True
    if conversation_history:
        for msg in conversation_history:
            if not msg.get("isBot", True) and any(pos in msg.get("message", "").lower() for pos in ["yes", "yeah", "yep", "correct", "i do", "i have", "multiple", "recurring", "chronic", "often", "frequently"]):
                for prev_msg in conversation_history:
                    if prev_msg.get("isBot", False) and "multiple times" in prev_msg.get("message", "").lower():
                        is_first_occurrence = False
                        break
    
    return {
        "is_question": is_question,
        "is_assessment": not is_question,
        "possible_conditions": response_text,
        "triage_level": triage_level,
        "requires_upgrade": requires_upgrade,
        "confidence": confidence,  # Always include confidence in the response
        "conditionName": condition_name if not is_question else None,  # Add condition name for display
        "is_first_occurrence": is_first_occurrence  # Add first occurrence flag
    }