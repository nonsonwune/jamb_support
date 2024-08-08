# gemini_processor.py
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Callable
from dotenv import load_dotenv
import google.generativeai as genai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from google.api_core.exceptions import ResourceExhausted, InvalidArgument
from utils import save_single_ticket_to_json
from config import MAX_RETRIES, RETRY_DELAY, API_CALL_LIMIT
from validation import validate_message
from logger import StructuredLogger

logger = StructuredLogger(__name__)

load_dotenv()


class APIKeyManager:
    def __init__(self, api_keys: List[str]):
        self.api_keys = api_keys
        self.current_key_index = 0
        self.key_usage = {i: 0 for i in range(len(api_keys))}
        self.last_reset_time = datetime.now()

    def get_current_key(self) -> str:
        return self.api_keys[self.current_key_index]

    def rotate_key(self) -> str:
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        return self.get_current_key()

    def increment_usage(self):
        self.key_usage[self.current_key_index] += 1
        self._check_reset()

    def _check_reset(self):
        current_time = datetime.now()
        if current_time - self.last_reset_time >= timedelta(minutes=1):
            self.key_usage = {i: 0 for i in range(len(self.api_keys))}
            self.last_reset_time = current_time

    def get_least_used_key(self) -> str:
        least_used_index = min(self.key_usage, key=self.key_usage.get)
        self.current_key_index = least_used_index
        return self.get_current_key()


class CustomException(Exception):
    """Base class for custom exceptions"""

    def __init__(self, message="An error occurred"):
        self.message = message
        super().__init__(self.message)


class APIKeyInvalidError(CustomException):
    """Raised when an API key is invalid."""

    def __init__(self, key_index, message=None):
        self.key_index = key_index
        if message is None:
            message = f"API key at index {key_index} is invalid"
        super().__init__(message)


class RateLimitExceededError(CustomException):
    """Raised when the rate limit is exceeded."""

    def __init__(self, limit, message=None):
        self.limit = limit
        if message is None:
            message = f"Rate limit of {limit} calls exceeded"
        super().__init__(message)


class AllAPIKeysExhaustedError(CustomException):
    """Raised when all API keys have been exhausted."""

    def __init__(self, total_keys, message=None):
        self.total_keys = total_keys
        if message is None:
            message = f"All {total_keys} API keys have been exhausted"
        super().__init__(message)


class APIResponseValidationError(CustomException):
    """Raised when the API response fails validation."""

    def __init__(self, response, message=None):
        self.response = response
        if message is None:
            message = f"API response failed validation: {response}"
        super().__init__(message)


class GeminiProcessor:
    def __init__(
        self, time_func: Callable[[], datetime] = datetime.now, env_file: str = None
    ):
        if env_file:
            load_dotenv(env_file)
        self.api_key_manager = APIKeyManager(self._load_api_keys())
        self.api_call_count = 0
        self.time_func = time_func
        self.last_reset_time = self.time_func()
        self.initialize_gemini()

    def _load_api_keys(self) -> List[str]:
        keys = []
        for i in range(1, 11):
            key = os.getenv(f"GEMINI_API_KEY_{i}")
            if key:
                keys.append(key)
                logger.info(f"Loaded API key {i}")
            else:
                logger.warning(f"GEMINI_API_KEY_{i} not found in environment variables")

        if not keys:
            logger.error("No Gemini API keys found in environment variables")
            raise ValueError("No Gemini API keys found in environment variables")

        logger.info(f"Loaded {len(keys)} API keys")
        return keys

    def initialize_gemini(self):
        try:
            genai.configure(api_key=self.api_key_manager.get_current_key())
            self.model = genai.GenerativeModel("gemini-1.5-pro")
            logger.info(
                f"Initialized Gemini with API key {self.api_key_manager.current_key_index + 1}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {str(e)}")
            raise

    def check_rate_limit(self):
        current_time = self.time_func()
        if current_time - self.last_reset_time >= timedelta(minutes=1):
            self.api_call_count = 0
            self.last_reset_time = current_time

        if self.api_call_count >= API_CALL_LIMIT:
            raise RateLimitExceededError(
                f"Rate limit of {API_CALL_LIMIT} calls exceeded"
            )

        self.api_call_count += 1

    def construct_prompt(self, ticket: Dict[str, Any]) -> str:
        return f"""
        Generate a reply for this support ticket:
        Ticket: {json.dumps(ticket)}
        
        Format: {{"Hello [name], JAMB Support here,\\n\\n[reply]\\n\\nSincerely,\\nJAMB Support"}}
        
        Guidelines:
        - Address the specific issue in the ticket
        - Be professional and helpful
        - For admission acceptance, confirm it was through JAMB CAPS
        - Escalate complex issues to appropriate authorities
        - CAPS: Central Admission Processing System
        - AIP: Admission In Progress
        """

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=4, max=120),
        retry=(
            retry_if_exception_type(ResourceExhausted)
            | retry_if_exception_type(APIKeyInvalidError)
            | retry_if_exception_type(RateLimitExceededError)
        ),
    )
    def generate_reply(self, prompt: str) -> str:
        for _ in range(len(self.api_key_manager.api_keys)):
            try:
                self.check_rate_limit()
                response = self.model.generate_content(prompt)
                logger.debug(f"Raw response from API: {response.text}")
                return self.parse_and_validate_reply(response.text)
            except ResourceExhausted:
                logger.warning(
                    f"Rate limit reached for API key {self.api_key_manager.current_key_index + 1}. Rotating API key and retrying..."
                )
                self.api_key_manager.rotate_key()
                self.initialize_gemini()
                raise RateLimitExceededError("Gemini API rate limit exceeded")
            except InvalidArgument as e:
                if "API_KEY_INVALID" in str(e):
                    logger.error(
                        f"API key {self.api_key_manager.current_key_index + 1} is invalid. Rotating to next key."
                    )
                    self.api_key_manager.rotate_key()
                    self.initialize_gemini()
                    raise APIKeyInvalidError(
                        f"API key {self.api_key_manager.current_key_index} is invalid"
                    )
                else:
                    logger.error(f"Unexpected InvalidArgument: {str(e)}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error in generate_reply: {str(e)}")
                raise

        raise AllAPIKeysExhaustedError(
            "All API keys exhausted. Unable to generate reply."
        )

    def parse_and_validate_reply(self, raw_reply: str) -> str:
        try:
            logger.debug(f"Raw reply from API: {raw_reply}")
            # Remove any leading/trailing whitespace and newlines
            cleaned_reply = raw_reply.strip()
            logger.debug(f"Cleaned reply: {cleaned_reply}")

            # Remove any markdown code block indicators
            if cleaned_reply.startswith("```json"):
                cleaned_reply = cleaned_reply[7:]
            if cleaned_reply.endswith("```"):
                cleaned_reply = cleaned_reply[:-3]

            # Try to parse as JSON
            try:
                parsed_reply = json.loads(cleaned_reply)
            except json.JSONDecodeError:
                logger.warning(
                    "JSON parsing failed, attempting direct content extraction"
                )
                # If JSON parsing fails, try to extract content directly
                content_start = cleaned_reply.find('"Hello')
                content_end = cleaned_reply.rfind('"')
                if content_start != -1 and content_end != -1:
                    content = cleaned_reply[content_start + 1 : content_end]
                    logger.info("Content extracted directly from malformed JSON")
                    return content

                # If direct extraction fails, raise an error
                raise APIResponseValidationError(
                    f"Failed to parse reply: {cleaned_reply}"
                )

            # If JSON parsing succeeds, extract the content
            if isinstance(parsed_reply, dict) and any(
                key.startswith("Hello") for key in parsed_reply
            ):
                content = next(
                    value
                    for key, value in parsed_reply.items()
                    if key.startswith("Hello")
                )
            else:
                raise APIResponseValidationError(
                    "Invalid reply format: missing 'Hello' key"
                )

            message = {
                "agent_name": "JAMB Support",
                "timestamp": self.time_func().strftime("%Y-%m-%d %H:%M:%S"),
                "content": content,
            }

            if not validate_message(message):
                raise APIResponseValidationError("Reply failed validation checks")

            logger.debug(f"Parsed and validated reply: {content}")
            return content
        except Exception as e:
            logger.error(f"Error in parse_and_validate_reply: {str(e)}")
            raise APIResponseValidationError(
                f"Failed to parse and validate reply: {str(e)}"
            )

    def process_tickets_batch(
        self, tickets: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        processed_tickets = []
        for ticket in tickets:
            try:
                prompt = self.construct_prompt(ticket)
                reply = self.generate_reply(prompt)
                ticket["next_reply"] = [{"content": reply}]
                save_single_ticket_to_json(ticket)
                processed_tickets.append(ticket)
                logger.info(
                    f"Successfully processed and saved ticket {ticket['ticket_id']}"
                )
            except RateLimitExceededError as e:
                logger.warning(
                    f"Rate limit exceeded for ticket {ticket['ticket_id']}: {str(e)}"
                )
                ticket["next_reply"] = [
                    {
                        "content": f"Processing delayed due to rate limiting. Please try again later."
                    }
                ]
                processed_tickets.append(ticket)
            except Exception as e:
                logger.error(
                    f"Failed to process ticket {ticket['ticket_id']}: {str(e)}"
                )
                ticket["next_reply"] = [
                    {
                        "content": f"An error occurred: {str(e)}. This ticket requires manual review."
                    }
                ]
                save_single_ticket_to_json(ticket)
                processed_tickets.append(ticket)
        return processed_tickets
