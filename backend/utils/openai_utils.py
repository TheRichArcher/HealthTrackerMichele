import openai
import logging
import os
import json
from backend.openai_config import get_openai_client

logger = logging.getLogger(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set.")

def call_openai_api(messages, response_format={"type": "json_object"}, retries=3):
    """
    Call OpenAI's API with robust error handling.
    """
    attempt = 0
    while attempt < retries:
        try:
            client = get_openai_client()
            response = client.chat.completions.create(
                model="gpt-4o-2024-05-13",  # Pinned to a specific version to prevent model updates
                messages=messages,
                response_format=response_format,
                max_tokens=1200,
                temperature=0.3  # Lowered from 0.7 to 0.3 for more deterministic behavior
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"OpenAI API call failed on attempt {attempt + 1}: {str(e)}")
            attempt += 1
            if attempt >= retries:
                logger.error("Exceeded maximum retry attempts for OpenAI API call")
                raise
            import time
            time.sleep(2 ** attempt)  # Exponential backoff

def clean_ai_response(raw_response):
    """
    Minimal utility to parse and set defaults for OpenAI responses.
    WARNING: This is a lightweight function and should NOT be used for the main symptom
    analysis flow in /symptoms/analyze. Use the clean_ai_response function in openai_config.py
    instead, as it includes critical validation logic for accurate assessments.
    """
    try:
        if isinstance(raw_response, str):
            response_data = json.loads(raw_response)
        elif isinstance(raw_response, dict):
            response_data = raw_response
        else:
            logger.error("Unexpected response format from OpenAI")
            raise ValueError("Unexpected OpenAI response format")

        # Set defaults if missing
        response_data.setdefault("is_assessment", False)
        response_data.setdefault("is_question", False)
        response_data.setdefault("possible_conditions", "")
        response_data.setdefault("confidence", None)
        response_data.setdefault("triage_level", None)
        response_data.setdefault("care_recommendation", None)
        response_data.setdefault("requires_upgrade", False)

        return response_data
    except Exception as e:
        logger.error(f"Error cleaning OpenAI response: {str(e)}", exc_info=True)
        raise