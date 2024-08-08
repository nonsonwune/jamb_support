# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_OUTPUT_DIR = os.path.join(BASE_DIR, "json")
MAX_RETRIES = 10
RETRY_DELAY = 5
MAX_PARALLEL_TABS = 3
SAVE_INTERVAL = 3
MINIMUM_MESSAGE_LENGTH = 1
API_CALL_LIMIT = 10
