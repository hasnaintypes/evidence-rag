import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.logging_config import configure_logging
from src.core.llm import generate_chat_response

configure_logging()

try:
    print("Response:", generate_chat_response("Hello"))
except Exception as e:
    print("Error:", e)
