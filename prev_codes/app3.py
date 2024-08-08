import os
import json
import random
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright
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
MAX_PARALLEL_TABS = 20
SAVE_INTERVAL = 20
MINIMUM_MESSAGE_LENGTH = 10

# Invalid message keywords
INVALID_KEYWORDS = [
    "Message *",
    "write here...",
    "Attachment",
    "File Type:",
    "Max file size:",
    "Send",
]


async def login_to_support(page):
    try:
        await page.goto("https://support.jamb.gov.ng/login")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_selector('input#email[type="email"]', state="visible")

        await page.fill('input#email[type="email"]', os.getenv("EMAIL"))
        await page.fill('input#password[type="password"]', os.getenv("PASSWORD"))

        await page.click('button[type="submit"]')
        await page.wait_for_url("**/tickets**")

        logger.info("Login Successful")
        return True
    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        return False


async def navigate_to_candidate_open_tickets_page(page, context):
    try:
        candidates_tickets_link = await page.wait_for_selector(
            'a#dashboard:has-text("Candidates Tickets")', state="visible"
        )
        async with context.expect_page() as new_page_info:
            await candidates_tickets_link.click()
        new_page = await new_page_info.value

        await new_page.wait_for_load_state("domcontentloaded")
        await new_page.wait_for_selector('th:has-text("Ticket ID")', state="visible")
        logger.info("Candidates Ticket Page Successful")

        await new_page.goto("https://support.jamb.gov.ng/agent/candidates-tickets?s=1")
        await new_page.wait_for_url("**/candidates-tickets?s=1")
        logger.info("Navigating to Candidate Open Ticket Successful")

        return new_page
    except Exception as e:
        logger.error(f"Navigation failed: {str(e)}")
        return None


async def navigate_to_ticket_page(page, ticket_id):
    for attempt in range(MAX_RETRIES):
        try:
            url = (
                f"https://support.jamb.gov.ng/agent/candidates-tickets/show/{ticket_id}"
            )
            await page.goto(url)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector(
                'h1:has-text("Ticket")', state="visible", timeout=60000
            )
            logger.info(f"Navigating to Ticket Page {ticket_id} Successful")
            return True
        except Exception as e:
            logger.warning(
                f"Attempt {attempt + 1} failed to navigate to ticket {ticket_id}: {str(e)}"
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error(
                    f"Failed to navigate to ticket {ticket_id} after {MAX_RETRIES} attempts"
                )
                return False


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


def validate_message(message):
    required_fields = ["timestamp", "content", "type"]
    sender_fields = ["sender_name", "agent_name"]

    for field in required_fields:
        if field not in message or not message[field]:
            return False

    if not any(field in message for field in sender_fields):
        return False

    # Check for unknown sender or timestamp
    if (
        message.get("sender_name", "") == "Unknown Sender"
        or message.get("agent_name", "") == "Unknown Sender"
    ):
        return False
    if message["timestamp"] == "Unknown Time":
        return False

    # Check for invalid keywords and message length
    content = message["content"]
    invalid_keyword_count = sum(keyword in content for keyword in INVALID_KEYWORDS)
    if invalid_keyword_count >= 4 or (
        invalid_keyword_count > 0 and len(content) < MINIMUM_MESSAGE_LENGTH
    ):
        return False

    return True


async def extract_messages(page, original_sender):
    try:
        await page.wait_for_selector(".timeline-item", state="visible", timeout=60000)
        messages = []
        message_elements = await page.query_selector_all(".timeline-item")

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
                content = content.strip()  # Remove leading/trailing whitespace

                header_element = await element.query_selector(".timeline-header")
                header_text = (
                    await header_element.inner_text() if header_element else ""
                )
                message_type = "sent" if "sent" in header_text else "replied"

                # Determine if the sender is the original sender or an agent
                sender_type = (
                    "sender_name"
                    if sender.lower() == original_sender.lower()
                    else "agent_name"
                )

                message = {
                    sender_type: sender,
                    "timestamp": timestamp,
                    "content": content,
                    "type": message_type,
                }

                if validate_message(message):
                    messages.append(message)
                else:
                    logger.warning(f"Skipping invalid message: {message}")

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


def redact_sensitive_info(ticket_data):
    redacted_data = ticket_data.copy()
    sensitive_fields = ["sender_email", "sender_phone"]
    for field in sensitive_fields:
        if field in redacted_data:
            redacted_data[field] = "REDACTED"
    return redacted_data


async def process_ticket(context, ticket_id, processed_tickets):
    page = await context.new_page()
    try:
        if await navigate_to_ticket_page(page, ticket_id):
            ticket_info = await extract_ticket_info(page)
            messages = await extract_messages(page, ticket_info.get("sender_name", ""))
            ticket_data = {**ticket_info, "messages": messages}

            if validate_ticket_data(ticket_data):
                processed_tickets.append(ticket_data)
                logger.info(f"Successfully processed ticket {ticket_id}")

                if len(processed_tickets) % 10 == 0:
                    redacted_sample = redact_sensitive_info(ticket_data)
                    logger.info(
                        f"Sample of extracted data: {json.dumps(redacted_sample, indent=2)}"
                    )
            else:
                logger.warning(f"Invalid ticket data for ticket ID: {ticket_id}")
        else:
            logger.warning(f"Failed to navigate to ticket {ticket_id}")
    except Exception as e:
        logger.error(f"Error processing ticket {ticket_id}: {str(e)}")
    finally:
        await page.close()
        await asyncio.sleep(random.uniform(0.5, 1.5))


async def main():
    processed_tickets = []
    resume_from = 0

    # Check if there's a progress file to resume from
    progress_file = "scraping_progress.json"
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            progress_data = json.load(f)
            processed_tickets = progress_data["processed_tickets"]
            resume_from = progress_data["next_ticket_index"]
        logger.info(f"Resuming from ticket index {resume_from}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            if not await login_to_support(page):
                return

            candidate_page = await navigate_to_candidate_open_tickets_page(
                page, context
            )
            if candidate_page:
                ticket_ids = await extract_ticket_ids(candidate_page)

                for i in range(resume_from, len(ticket_ids), MAX_PARALLEL_TABS):
                    batch = ticket_ids[i : i + MAX_PARALLEL_TABS]
                    tasks = [
                        process_ticket(context, ticket_id, processed_tickets)
                        for ticket_id in batch
                    ]
                    await asyncio.gather(*tasks)

                    logger.info(
                        f"Processed {i + len(batch)} out of {len(ticket_ids)} tickets"
                    )

                    if (i + len(batch)) % SAVE_INTERVAL == 0:
                        save_to_json(processed_tickets)
                        # Save progress
                        with open(progress_file, "w") as f:
                            json.dump(
                                {
                                    "processed_tickets": processed_tickets,
                                    "next_ticket_index": i + len(batch),
                                },
                                f,
                            )
                        logger.info(
                            f"Progress saved. Resumable from ticket index {i + len(batch)}"
                        )

                save_to_json(processed_tickets)
        except Exception as e:
            logger.error(f"An unexpected error occurred: {str(e)}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
