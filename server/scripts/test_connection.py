import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import generate_chat_response

try:
    print("Response:", generate_chat_response("Hello"))
except Exception as e:
    print("Error:", e)
