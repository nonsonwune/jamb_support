import os
import json
import random
import time
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import logging

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


def login_to_support(page):
    try:
        page.goto("https://support.jamb.gov.ng/login")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_selector('input#email[type="email"]', state="visible")

        page.fill('input#email[type="email"]', os.getenv("EMAIL"))
        page.fill('input#password[type="password"]', os.getenv("PASSWORD"))

        page.click('button[type="submit"]')
        page.wait_for_url("**/tickets**")

        logger.info("Login Successful")
        return True
    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        return False


def navigate_to_candidate_open_tickets_page(page, context):
    try:
        candidates_tickets_link = page.wait_for_selector(
            'a#dashboard:has-text("Candidates Tickets")', state="visible"
        )
        with context.expect_page() as new_page_info:
            candidates_tickets_link.click()
        new_page = new_page_info.value

        new_page.wait_for_load_state("domcontentloaded")
        new_page.wait_for_selector('th:has-text("Ticket ID")', state="visible")
        logger.info("Candidates Ticket Page Successful")

        new_page.goto("https://support.jamb.gov.ng/agent/candidates-tickets?s=1")
        new_page.wait_for_url("**/candidates-tickets?s=1")
        logger.info("Navigating to Candidate Open Ticket Successful")

        return new_page
    except Exception as e:
        logger.error(f"Navigation failed: {str(e)}")
        return None


def navigate_to_ticket_page(page, ticket_id):
    for attempt in range(MAX_RETRIES):
        try:
            url = (
                f"https://support.jamb.gov.ng/agent/candidates-tickets/show/{ticket_id}"
            )
            page.goto(url)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_selector(
                'h1:has-text("Ticket")', state="visible", timeout=60000
            )
            logger.info(f"Navigating to Ticket Page {ticket_id} Successful")
            return True
        except Exception as e:
            logger.warning(
                f"Attempt {attempt + 1} failed to navigate to ticket {ticket_id}: {str(e)}"
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                logger.error(
                    f"Failed to navigate to ticket {ticket_id} after {MAX_RETRIES} attempts"
                )
                return False


def extract_ticket_ids(page):
    try:
        page.wait_for_selector("table#DataTables_Table_0")
        ticket_ids = page.eval_on_selector_all(
            "table#DataTables_Table_0 tbody tr td:first-child a",
            "elements => elements.map(el => el.textContent.trim())",
        )
        logger.info(f"Extracted {len(ticket_ids)} Ticket IDs")
        return ticket_ids
    except Exception as e:
        logger.error(f"Failed to extract Ticket IDs: {str(e)}")
        return []


def extract_ticket_info(page):
    try:
        page.wait_for_selector(".row .table", state="visible", timeout=60000)

        ticket_info = {}

        # Extract information from the first table
        first_table = page.query_selector(".row .col-md-6:first-child .table")
        rows = first_table.query_selector_all("tr")
        for row in rows:
            key = (
                row.query_selector("th").inner_text().strip().lower().replace("/", "_")
            )
            value = row.query_selector("td").inner_text().strip()
            ticket_info[key] = value

        # Extract information from the second table
        second_table = page.query_selector(".row .col-md-6:last-child .table")
        rows = second_table.query_selector_all("tr")
        for row in rows:
            key = (
                row.query_selector("th").inner_text().strip().lower().replace(" ", "_")
            )
            value = row.query_selector("td").inner_text().strip()
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


def extract_messages(page):
    try:
        page.wait_for_selector(".timeline-item", state="visible", timeout=60000)
        messages = []
        message_elements = page.query_selector_all(".timeline-item")

        for element in message_elements:
            try:
                sender_element = element.query_selector(".timeline-header a")
                sender = (
                    sender_element.inner_text().strip()
                    if sender_element
                    else "Unknown Sender"
                )

                timestamp_element = element.query_selector(".time")
                timestamp = (
                    timestamp_element.inner_text().strip()
                    if timestamp_element
                    else "Unknown Time"
                )

                content_element = element.query_selector(".timeline-body")
                content = (
                    content_element.inner_text().strip()
                    if content_element
                    else "No content"
                )

                header_element = element.query_selector(".timeline-header")
                message_type = (
                    "sent"
                    if header_element and "sent" in header_element.inner_text()
                    else "replied"
                )

                messages.append(
                    {
                        "sender_name": sender,
                        "timestamp": timestamp,
                        "content": content,
                        "type": message_type,
                    }
                )

            except Exception as inner_e:
                logger.warning(f"Failed to extract a message: {str(inner_e)}")

        if not messages:
            logger.warning("No messages were extracted from the ticket")
        else:
            logger.info(f"Extracted {len(messages)} messages")

        return messages
    except Exception as e:
        logger.error(f"Failed to extract messages: {str(e)}")
        return []


# Also, let's update the validate_ticket_data function to be more lenient:
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
    ]
    for field in required_fields:
        if field not in ticket_data or not ticket_data[field]:
            logger.warning(f"Missing or empty required field: {field}")
            return False

    if "messages" not in ticket_data or not isinstance(ticket_data["messages"], list):
        logger.warning("Messages field is missing or not a list")
        return False

    return True


def save_to_json(data, filename=None):
    if filename is None:
        filename = f"tickets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(filename, "w", encoding="utf-8") as jsonfile:
            json.dump(data, jsonfile, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(data)} tickets to {filename}")
    except Exception as e:
        logger.error(f"Failed to save tickets to JSON: {str(e)}")


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
            logger.warning(f"Missing or empty required field: {field}")
            return False
    return True


def main():
    tickets_data = []
    with sync_playwright() as playwright:
        browser = None
        try:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()

            if not login_to_support(page):
                return

            candidate_page = navigate_to_candidate_open_tickets_page(page, context)
            if candidate_page:
                ticket_ids = extract_ticket_ids(candidate_page)
                for ticket_id in ticket_ids:
                    if navigate_to_ticket_page(candidate_page, ticket_id):
                        ticket_info = extract_ticket_info(candidate_page)
                        messages = extract_messages(candidate_page)
                        ticket_data = {**ticket_info, "messages": messages}

                        if validate_ticket_data(ticket_data):
                            tickets_data.append(ticket_data)
                        else:
                            logger.warning(
                                f"Skipping invalid ticket data for ticket ID: {ticket_id}"
                            )

                        # Add a random delay between requests
                        time.sleep(random.uniform(1, 3))

                save_to_json(tickets_data)
        except Exception as e:
            logger.error(f"An unexpected error occurred: {str(e)}")
        finally:
            if browser:
                browser.close()


if __name__ == "__main__":
    main()
