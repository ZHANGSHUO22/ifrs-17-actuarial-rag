# backend/app/services/llm/gemini_client.py
import os
import asyncio
import google.generativeai as genai

class GeminiClient:
    """
    LLM Client configured for Debug Mode using Gemma 3.
    """
    def __init__(self, api_key: str = None):
        # 1. Standardize API Key: Use GOOGLE_API_KEY
        google_key = os.getenv("GOOGLE_API_KEY") or api_key
        if not google_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set.")
            
        genai.configure(api_key=google_key)
        
        # 2. Configurable Model Name: Load from environment variable
        model_name = os.getenv("LLM_MODEL_NAME", "models/gemini-1.5-flash")
        
        print(f"Initializing LLM Client with model: {model_name}")
        self.model = genai.GenerativeModel(model_name=model_name)

    async def generate(self, prompt: str) -> str:
        """
        Asynchronously generates content using the configured model.
        """
        # Wrapping the synchronous SDK call in a thread to keep it non-blocking
        response = await asyncio.to_thread(
            self.model.generate_content,
            prompt
        )
        
        if not response or not response.text:
            return "Error: LLM returned an empty response."
            
        return response.text
