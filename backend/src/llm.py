from google import genai
from google.genai import types
from src.config import settings
from typing import List, Optional

# Tracked so db.py can flag a change of embedding model, which would
# produce vectors of a different dimension than what's already indexed.
EMBEDDING_MODEL_NAME = settings.gemini_embedding_model

client = genai.Client(api_key=settings.gemini_api_key)


def get_embedding(text: str) -> List[float]:
    """
    Generates a vector embedding for the provided text via the Gemini API.
    """
    clean_text = text.replace("\n", " ")
    result = client.models.embed_content(model=settings.gemini_embedding_model, contents=clean_text)
    return result.embeddings[0].values


def generate_chat_response(prompt: str, max_tokens: Optional[int] = None) -> str:
    """
    Sends the augmented prompt to Gemini and returns the response.

    max_tokens: overrides settings.generation_max_tokens for this call.
    Useful for short, structured outputs (e.g. entity extraction JSON
    arrays, sub-query decomposition) where the default long-answer
    budget wastes tokens for no benefit.
    """
    try:
        response = client.models.generate_content(
            model=settings.gemini_chat_model,
            contents=f"You are an intelligent AI assistant.\n\n{prompt}",
            config=types.GenerateContentConfig(
                temperature=settings.generation_temperature,
                max_output_tokens=max_tokens if max_tokens is not None else settings.generation_max_tokens,
            ),
        )
        return response.text
    except Exception as e:
        return f"Error during generation: {str(e)}"
