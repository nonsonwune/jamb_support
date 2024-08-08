# validation.py

from config import MINIMUM_MESSAGE_LENGTH
from logger import StructuredLogger

logger = StructuredLogger(__name__)


def validate_message(message):
    # Check for the specific invalid message pattern
    if (
        message.get("agent_name") == "Unknown Sender"
        and message.get("timestamp") in ["N/A", "Unknown Time"]
        and "Message * write here..." in message.get("content", "")
        and "File Type:" in message.get("content", "")
        and "Max file size:" in message.get("content", "")
    ):
        logger.warning(f"Invalid message pattern detected: {message}")
        return False

    # Check for minimum content length
    if len(message.get("content", "").strip()) < MINIMUM_MESSAGE_LENGTH:
        logger.warning(f"Message content too short: {message}")
        return False

    # Additional check for "Unknown Sender" with "Unknown Time"
    if (
        message.get("agent_name") == "Unknown Sender"
        and message.get("timestamp") == "Unknown Time"
    ):
        logger.warning(
            f"Invalid message detected (Unknown Sender with Unknown Time): {message}"
        )
        return False

    logger.info(f"Valid message: {message}")
    return True


def validate_ticket_data(ticket_data):
    required_fields = [
        "ticket_id",
        "status",
        "service_system",
        "issue",
        "sender_name",
        "sender_email",
        "sender_phone",
        "agent_name",
        "messages",
    ]
    for field in required_fields:
        if field not in ticket_data or not ticket_data[field]:
            if field in ["sender_email", "sender_phone"]:
                ticket_data[field] = "N/A"
                logger.info(
                    f"Set missing {field} to N/A for ticket {ticket_data.get('ticket_id', 'Unknown')}"
                )
            else:
                logger.warning(
                    f"Missing or empty required field: {field} for ticket {ticket_data.get('ticket_id', 'Unknown')}"
                )
                return False

    # Ensure that at least one valid message exists in the ticket
    if not ticket_data["messages"]:
        logger.warning(
            f"No valid messages found for ticket {ticket_data.get('ticket_id', 'Unknown')}"
        )
        return False

    logger.info(
        f"Ticket {ticket_data.get('ticket_id', 'Unknown')} validated successfully"
    )
    return True
