import os
from typing import List

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr


class GeminiRotator:
    """
    Reads GEMINI_API_KEY and GEMINI_KEY_* from a specified .env file
    and provides a round-robin rotation for LangChain ChatGoogleGenerativeAI instances.
    """
    def __init__(self, env_path: str = "/home/kizabgd/Desktop/kaggle-arena/.env"):
        load_dotenv(env_path)
        self.keys = self._load_keys()
        self.current_idx = 0
        
        if not self.keys:
            raise ValueError(f"No Gemini keys found in {env_path}")
            
    def _load_keys(self) -> List[str]:
        keys = []
        # Main key
        main_key = os.getenv("GEMINI_API_KEY")
        if main_key:
            keys.append(main_key)
            
        # Indexed keys from 1 to 50
        for i in range(1, 51):
            key = os.getenv(f"GEMINI_KEY_{i}")
            if key and key not in keys:
                keys.append(key)
                
        return keys
        
    def get_next_key(self) -> str:
        """Returns the next key in the rotation logic."""
        key = self.keys[self.current_idx]
        self.current_idx = (self.current_idx + 1) % len(self.keys)
        return key

    def get_model(self, model_name: str = "gemini-3-flash-preview", temperature: float = 0.3, **kwargs) -> ChatGoogleGenerativeAI:
        """
        Returns a ChatGoogleGenerativeAI instance using the next available key.
        """
        api_key = self.get_next_key()
        print(f"DEBUG: Using Gemini Key #{self.current_idx} for {model_name}")
        return ChatGoogleGenerativeAI(
            model=model_name,
            api_key=SecretStr(api_key),
            temperature=temperature,
            **kwargs
        )

# Global instance for easy importing
rotator = GeminiRotator()

def get_rotated_gemini_model(model_name: str = "gemini-3-flash-preview", **kwargs) -> ChatGoogleGenerativeAI:
    """Convenience function to get the next model in rotation."""
    return rotator.get_model(model_name=model_name, **kwargs)
