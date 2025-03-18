# backend/utils/openai_utils.py
import openai
import os
import logging
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Constants
MODEL_NAME = "gpt-4o"
MAX_TOKENS = 1000
TEMPERATURE = 0.7
MAX_RETRIES = 3
BASE_RETRY_DELAY = 2

# Set up OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set.")

@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=BASE_RETRY_DELAY, max=10),
    retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError, openai.APIError))
)
def call_openai_api(messages, response_format=None, max_tokens=MAX_TOKENS, temperature=TEMPERATURE):
    """Call the OpenAI API with retry logic and error handling."""
    try:
        logger.debug(f"Sending OpenAI request with prompt: {messages[-1]['content'][:100]}...")
        response = openai.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format
        )
        content = response.choices[0].message.content.strip()
        if not content:
            logger.warning("Empty response from OpenAI, retrying...")
            raise openai.OpenAIError("Empty response")
        logger.debug(f"OpenAI response: {content[:100]}...")
        return content
    except openai.AuthenticationError as e:
        logger.error(f"OpenAI authentication error: {str(e)}")
        raise
    except openai.InvalidRequestError as e:
        logger.error(f"OpenAI invalid request error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected OpenAI API error: {str(e)}", exc_info=True)
        raise