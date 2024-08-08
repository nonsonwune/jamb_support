# utils.py

import json
import os
from datetime import datetime
from logger import StructuredLogger
from config import JSON_OUTPUT_DIR

logger = StructuredLogger(__name__)


def save_single_ticket_to_json(ticket):
    filename = os.path.join(
        JSON_OUTPUT_DIR, f"tickets_{datetime.now().strftime('%Y%m%d')}.json"
    )
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        if os.path.exists(filename):
            with open(filename, "r+", encoding="utf-8") as jsonfile:
                try:
                    data = json.load(jsonfile)
                except json.JSONDecodeError:
                    data = []
                data.append(ticket)
                jsonfile.seek(0)
                json.dump(data, jsonfile, ensure_ascii=False, indent=2)
                jsonfile.truncate()
        else:
            with open(filename, "w", encoding="utf-8") as jsonfile:
                json.dump([ticket], jsonfile, ensure_ascii=False, indent=2)
        logger.info(f"Saved ticket {ticket.get('ticket_id', 'Unknown')} to {filename}")
    except Exception as e:
        logger.error(
            f"Failed to save ticket {ticket.get('ticket_id', 'Unknown')} to JSON: {str(e)}",
            extra={
                "exception": str(e),
                "ticket_id": ticket.get("ticket_id", "Unknown"),
            },
        )
        logger.error(f"Current working directory: {os.getcwd()}")
        logger.error(f"File path attempted: {os.path.abspath(filename)}")


def save_to_json(data, filename=None):
    if filename is None:
        filename = f"tickets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(filename, "w", encoding="utf-8") as jsonfile:
            json.dump(data, jsonfile, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(data)} tickets to {filename}")
    except Exception as e:
        logger.error(
            f"Failed to save tickets to JSON: {str(e)}", extra={"exception": str(e)}
        )


def redact_sensitive_info(ticket_data):
    redacted_data = ticket_data.copy()
    sensitive_fields = ["sender_email", "sender_phone"]
    for field in sensitive_fields:
        if field in redacted_data:
            redacted_data[field] = "REDACTED"
    return redacted_data


def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        try:
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")
        except Exception as e:
            logger.error(
                f"Failed to create directory {directory}: {str(e)}",
                extra={"exception": str(e), "directory": directory},
            )
            raise
