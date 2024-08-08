# extraction.py

import asyncio
import random
from logger import StructuredLogger
from validation import validate_message, validate_ticket_data
from navigation import navigate_to_ticket_page
from utils import redact_sensitive_info
from validation import validate_message, validate_ticket_data
import json

logger = StructuredLogger(__name__)


async def extract_ticket_ids(page):
    try:
        await page.wait_for_selector("table#DataTables_Table_0")
        ticket_ids = await page.eval_on_selector_all(
            "table#DataTables_Table_0 tbody tr td:first-child a",
            "elements => elements.map(el => el.textContent.trim())",
        )
        logger.info(f"Extracted {len(ticket_ids)} Ticket IDs")
        return ticket_ids
    except Exception as e:
        logger.error(f"Failed to extract Ticket IDs: {str(e)}")
        return []


async def extract_ticket_info(page):
    try:
        await page.wait_for_selector(".row .table", state="visible", timeout=60000)

        ticket_info = {}

        # Extract information from the first table
        first_table = await page.query_selector(".row .col-md-6:first-child .table")
        rows = await first_table.query_selector_all("tr")
        for row in rows:
            th = await row.query_selector("th")
            td = await row.query_selector("td")
            key = (await th.inner_text()).strip().lower().replace("/", "_")
            value = (await td.inner_text()).strip()
            ticket_info[key] = value

        # Extract information from the second table
        second_table = await page.query_selector(".row .col-md-6:last-child .table")
        rows = await second_table.query_selector_all("tr")
        for row in rows:
            th = await row.query_selector("th")
            td = await row.query_selector("td")
            key = (await th.inner_text()).strip().lower().replace(" ", "_")
            value = (await td.inner_text()).strip()
            ticket_info[key] = value

        # Rename keys to match the desired output format
        key_mapping = {
            "reference": "ticket_id",
            "from": "sender_name",
            "email": "sender_email",
            "phone": "sender_phone",
            "assigned_to": "agent_name",
        }
        for old_key, new_key in key_mapping.items():
            if old_key in ticket_info:
                ticket_info[new_key] = ticket_info.pop(old_key)

        logger.info(
            f"Successfully extracted info for ticket {ticket_info.get('ticket_id', 'Unknown')}"
        )
        return ticket_info
    except Exception as e:
        logger.error(f"Failed to extract ticket info: {str(e)}")
        return {}


def normalize_name(name):
    """Normalize a name by removing extra spaces and converting to lowercase."""
    return " ".join(name.lower().split())


async def extract_messages(page, original_sender):
    try:
        await page.wait_for_selector(".timeline-item", state="visible", timeout=60000)
        messages = []
        message_elements = await page.query_selector_all(".timeline-item")
        original_sender_normalized = normalize_name(original_sender)

        for element in message_elements:
            try:
                sender_element = await element.query_selector(".timeline-header a")
                sender = (
                    await sender_element.inner_text()
                    if sender_element
                    else "Unknown Sender"
                )

                timestamp_element = await element.query_selector(".time")
                timestamp = (
                    await timestamp_element.inner_text()
                    if timestamp_element
                    else "Unknown Time"
                )

                content_element = await element.query_selector(".timeline-body")
                content = (
                    await content_element.inner_text()
                    if content_element
                    else "No content"
                )
                content = content.strip()

                header_element = await element.query_selector(".timeline-header")
                header_text = (
                    await header_element.inner_text() if header_element else ""
                )
                message_type = "sent" if "sent" in header_text else "replied"

                # Determine if the sender is the original sender or an agent
                if normalize_name(sender) == original_sender_normalized:
                    sender_type = "sender_name"
                else:
                    sender_type = "agent_name"

                message = {
                    sender_type: sender,
                    "timestamp": timestamp,
                    "content": content,
                    "type": message_type,
                }

                logger.info(f"Validating message: {message}")
                if validate_message(message):
                    messages.append(message)
                    logger.info(f"Message added to valid messages: {message}")
                else:
                    logger.warning(f"Invalid message skipped: {message}")

            except Exception as inner_e:
                logger.warning(f"Failed to extract a message: {str(inner_e)}")

        if not messages:
            logger.warning("No valid messages were extracted from the ticket")
        else:
            logger.info(f"Extracted {len(messages)} valid messages")

        return messages
    except Exception as e:
        logger.error(f"Failed to extract messages: {str(e)}")
        return []


async def process_ticket(context, ticket_id, processed_tickets):
    page = await context.new_page()
    try:
        if await navigate_to_ticket_page(page, ticket_id):
            ticket_info = await extract_ticket_info(page)
            all_messages = await extract_messages(
                page, ticket_info.get("sender_name", "")
            )

            # Filter out invalid messages
            valid_messages = [msg for msg in all_messages if validate_message(msg)]

            ticket_data = {**ticket_info, "messages": valid_messages}

            if not valid_messages:
                ticket_data["needs_review"] = True
                logger.warning(
                    f"Ticket {ticket_id} has no valid messages and needs review"
                )

            if validate_ticket_data(ticket_data):
                processed_tickets.append(ticket_data)
                logger.info(f"Successfully processed ticket {ticket_id}")
            else:
                logger.warning(f"Invalid ticket data for ticket ID: {ticket_id}")
        else:
            logger.warning(f"Failed to navigate to ticket {ticket_id}")
    except Exception as e:
        logger.error(f"Error processing ticket {ticket_id}: {str(e)}")
    finally:
        await page.close()
        await asyncio.sleep(random.uniform(0.5, 1.5))
