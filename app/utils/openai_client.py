import openai
from app.core.config import settings
from typing import Dict, Any, Optional

openai.api_key = settings.OPENAI_API_KEY

# For OpenAI's Chat API (gpt-3.5-turbo, gpt-4, etc.)
def get_openai_completion(prompt: str, ai_config: Optional[Dict[str, Any]] = None) -> str:
    """
    Get AI completion for the given prompt with optional configuration.
    
    Args:
        prompt: The prompt to send to AI
        ai_config: Optional AI configuration (max_tokens, temperature, etc.)
        
    Returns:
        AI response content as string
    """
    # Use default config if none provided
    if ai_config is None:
        ai_config = {
            "max_tokens": 512,
            "temperature": 0.7
        }
    
    # Extract configuration parameters
    max_tokens = ai_config.get("max_tokens", 512)
    temperature = ai_config.get("temperature", 0.7)
    
    try:
        response = openai.ChatCompletion.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful financial modeling assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        # Check if response is valid
        if not response or not response.choices or len(response.choices) == 0:
            raise Exception("OpenAI returned empty response")
        
        content = response.choices[0].message["content"]
        if not content:
            raise Exception("OpenAI returned empty content")
        
        return content.strip()
        
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"OpenAI API error: {str(e)}")
        logger.error(f"Prompt: {prompt[:200]}...")
        raise Exception(f"OpenAI API failed: {str(e)}") 