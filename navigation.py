# navigation.py
import asyncio
from logger import StructuredLogger
from config import MAX_RETRIES, RETRY_DELAY

logger = StructuredLogger(__name__)


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
