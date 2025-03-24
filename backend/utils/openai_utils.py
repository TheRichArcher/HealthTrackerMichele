import logging
import os
from typing import Optional
from openai import OpenAI

# Configure logging
logger = logging.getLogger(__name__)

def get_openai_client():
    """Returns an OpenAI client instance using the API key from environment variables."""
    api_key = os.getenv("OPENAI_API_KEY")
    return OpenAI(api_key=api_key)

def build_openai_messages(system_prompt: str, symptom_input: str, conversation_history: Optional[list] = None, additional_instructions: str = "") -> list:
    """Build OpenAI message structure, incorporating conversation history if provided."""
    messages = [{"role": "system", "content": system_prompt}]
    
    if conversation_history:
        for entry in conversation_history:
            role = "assistant" if entry.get("isBot", False) else "user"
            messages.append({"role": role, "content": entry["message"]})
    
    messages.append({"role": "user", "content": symptom_input})
    
    if additional_instructions:
        messages.append({"role": "system", "content": additional_instructions})
    
    return messages

def call_openai_api(messages: list, max_tokens: int = 300, response_format: Optional[dict] = None) -> str:
    """Call OpenAI API with the provided messages."""
    client = get_openai_client()
    try:
        params = {
            "model": "gpt-4o",  # Changed from "gpt-4o-mini" to "gpt-4o"
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        if response_format:
            params["response_format"] = response_format
        
        response = client.chat.completions.create(**params)
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API call failed: {str(e)}", exc_info=True)
        raise