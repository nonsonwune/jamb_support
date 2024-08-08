# unit_test.py
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import json
from gemini_processor import (
    GeminiProcessor,
    APIKeyInvalidError,
    RateLimitExceededError,
    AllAPIKeysExhaustedError,
    APIResponseValidationError,
)
from google.api_core.exceptions import ResourceExhausted, InvalidArgument
from config import API_CALL_LIMIT, MAX_RETRIES


class TestGeminiProcessorIntegration(unittest.TestCase):
    def setUp(self):
        self.time_func = MagicMock(return_value=datetime(2024, 1, 1, 0, 0, 0))
        self.processor = GeminiProcessor(time_func=self.time_func)

    def test_construct_prompt(self):
        test_ticket = {
            "sender_name": "John Doe",
            "ticket_id": "#TEST-001",
            "messages": [{"content": "Test message"}],
        }
        prompt = self.processor.construct_prompt(test_ticket)
        self.assertIn("Hello John Doe, Welcome JAMB Support System,", prompt)
        self.assertIn(json.dumps(test_ticket), prompt)

    @patch("google.generativeai.GenerativeModel.generate_content")
    def test_successful_api_call(self, mock_generate_content):
        mock_generate_content.return_value.text = '{"content": "Hello John, JAMB Support here,\\n\\nThis is a test reply.\\n\\nSincerely,\\nJAMB Support"}'
        result = self.processor.generate_reply("Test prompt")
        self.assertIn("Hello John, JAMB Support here", result)

    @patch("google.generativeai.GenerativeModel.generate_content")
    def test_rate_limit_with_recovery(self, mock_generate_content):
        mock_generate_content.side_effect = [
            ResourceExhausted("Rate limit exceeded"),
            MagicMock(
                text='{"content": "Hello Jane, JAMB Support here,\\n\\nThis is a test reply.\\n\\nSincerely,\\nJAMB Support"}'
            ),
        ]
        result = self.processor.generate_reply("Test prompt")
        self.assertIn("Hello Jane, JAMB Support here", result)

    @patch("google.generativeai.GenerativeModel.generate_content")
    def test_persistent_api_error(self, mock_generate_content):
        mock_generate_content.side_effect = [InvalidArgument("API_KEY_INVALID")] * (
            MAX_RETRIES + 1
        )
        with self.assertRaises(AllAPIKeysExhaustedError):
            self.processor.generate_reply("Test prompt")
        self.assertEqual(mock_generate_content.call_count, MAX_RETRIES)

    @patch("gemini_processor.save_single_ticket_to_json")
    def test_process_tickets_batch(self, mock_save):
        test_tickets = [
            {
                "ticket_id": "#TEST-001",
                "sender_name": "Test User",
                "messages": [{"content": "Test message"}],
            }
        ]
        with patch.object(
            self.processor,
            "generate_reply",
            return_value="Hello Test User, JAMB Support here,\n\nThis is a test reply.\n\nSincerely,\nJAMB Support",
        ):
            processed_tickets = self.processor.process_tickets_batch(test_tickets)

        self.assertEqual(len(processed_tickets), 1)
        self.assertIn(
            "Hello Test User, JAMB Support here",
            processed_tickets[0]["next_reply"][0]["content"],
        )

    def test_api_key_rotation(self):
        initial_key_index = self.processor.api_key_manager.current_key_index
        self.processor.api_key_manager.rotate_key()
        self.assertNotEqual(
            initial_key_index, self.processor.api_key_manager.current_key_index
        )

    @patch("google.generativeai.GenerativeModel.generate_content")
    def test_api_key_rotation_on_resource_exhausted(self, mock_generate_content):
        mock_generate_content.side_effect = [
            ResourceExhausted("Rate limit exceeded"),
            MagicMock(
                text='{"content": "Hello User, JAMB Support here,\\n\\nThis is a test reply.\\n\\nSincerely,\\nJAMB Support"}'
            ),
        ]
        initial_key_index = self.processor.api_key_manager.current_key_index
        result = self.processor.generate_reply("Test prompt")
        self.assertNotEqual(
            initial_key_index, self.processor.api_key_manager.current_key_index
        )
        self.assertIn("Hello User, JAMB Support here", result)

    @patch("google.generativeai.GenerativeModel.generate_content")
    def test_api_key_rotation_on_invalid_key(self, mock_generate_content):
        mock_generate_content.side_effect = [
            InvalidArgument("API_KEY_INVALID"),
            MagicMock(
                text='{"content": "Hello User, JAMB Support here,\\n\\nThis is a test reply.\\n\\nSincerely,\\nJAMB Support"}'
            ),
        ]
        initial_key_index = self.processor.api_key_manager.current_key_index
        result = self.processor.generate_reply("Test prompt")
        self.assertNotEqual(
            initial_key_index, self.processor.api_key_manager.current_key_index
        )
        self.assertIn("Hello User, JAMB Support here", result)

    def test_rate_limit_reset(self):
        for _ in range(API_CALL_LIMIT):
            self.processor.check_rate_limit()

        # Simulate 1 minute passing
        self.time_func.return_value += timedelta(minutes=1)

        # This should not raise an exception as the rate limit should have reset
        self.processor.check_rate_limit()

    def test_parse_and_validate_reply_with_json(self):
        raw_reply = '{"content": "Hello John Doe, JAMB Support here,\\n\\nThis is a test reply.\\n\\nSincerely,\\nJAMB Support"}'
        result = self.processor.parse_and_validate_reply(raw_reply)
        self.assertEqual(
            result,
            "Hello John Doe, JAMB Support here,\n\nThis is a test reply.\n\nSincerely,\nJAMB Support",
        )

    def test_parse_and_validate_reply_with_markdown(self):
        raw_reply = '```json\n{"content": "Hello User, JAMB Support here,\\n\\nThis is a test reply.\\n\\nSincerely,\\nJAMB Support"}\n```'
        result = self.processor.parse_and_validate_reply(raw_reply)
        self.assertIn("Hello User, JAMB Support here", result)

    def test_parse_and_validate_reply_invalid_json(self):
        raw_reply = "Invalid JSON"
        with self.assertRaises(APIResponseValidationError):
            self.processor.parse_and_validate_reply(raw_reply)

    def test_parse_and_validate_reply_missing_content_key(self):
        raw_reply = '{"InvalidKey": "Value"}'
        with self.assertRaises(APIResponseValidationError):
            self.processor.parse_and_validate_reply(raw_reply)

    def test_parse_and_validate_reply_malformed_json(self):
        raw_reply = '```json\n{"content": "Hello [name], JAMB Support here,\\n\\nThis is a test reply.\\n\\nSincerely,\\nJAMB Support"}\n```'
        result = self.processor.parse_and_validate_reply(raw_reply)
        self.assertIn("Hello [name], JAMB Support here", result)

    def test_parse_and_validate_reply_with_square_brackets(self):
        raw_reply = '{"content": "Hello [John Doe], JAMB Support here,\\n\\nThis is a test reply.\\n\\nSincerely,\\nJAMB Support"}'
        result = self.processor.parse_and_validate_reply(raw_reply)
        self.assertIn("Hello [John Doe]", result)

    def test_parse_and_validate_reply_direct_extraction(self):
        raw_reply = "Hello Jane Doe, JAMB Support here,\n\nThis is a test reply.\n\nSincerely,\nJAMB Support"
        result = self.processor.parse_and_validate_reply(raw_reply)
        self.assertEqual(result, raw_reply)

    def test_format_reply(self):
        content = "Hello [John Doe], JAMB Support here,\n\nThis is a test reply.\n\nSincerely,\nJAMB Support"
        result = self.processor._format_reply(content)
        self.assertIn("Hello John Doe", result)
        self.assertNotIn("[John Doe]", result)


if __name__ == "__main__":
    unittest.main()
