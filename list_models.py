import os

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv("/home/kizabgd/Desktop/kaggle-arena/.env")
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("Error: GEMINI_API_KEY not found in .env")
    exit(1)

genai.configure(api_key=api_key)

print(f"Listing models for key starting with: {api_key[:10]}...")
try:
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"Error listing models: {e}")
