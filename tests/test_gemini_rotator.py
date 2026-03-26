import os
import sys

# Add root directory to sys.path to resolve 'utils'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_core.messages import HumanMessage

from utils.gemini_rotator import get_rotated_gemini_model, rotator


def test_rotation():
    print(f"Total keys loaded: {len(rotator.keys)}")
    
    # Do 3 rapid calls to check if the keys rotate and work
    for i in range(3):
        print(f"\n--- Call {i+1} ---")
        model = get_rotated_gemini_model()
        print(f"Using model: {model.model}")
        
        try:
            response = model.invoke([HumanMessage(content=f"Say simply: 'Testing call {i+1}'")])
            print("Response:", response.content.strip())
        except Exception as e:
            print("Error:", str(e))

if __name__ == "__main__":
    test_rotation()
