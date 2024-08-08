# check_agent_last_reply.py
import asyncio
import json
from playwright.async_api import async_playwright
import os
from dotenv import load_dotenv

# Import necessary functions from existing files
from login import login_to_support
from navigation import navigate_to_candidate_open_tickets_page
from extraction import extract_ticket_ids, extract_ticket_info, extract_messages
from validation import validate_message
from logger import logger

load_dotenv()


async def extract_ticket_data(context, ticket_id):
    page = await context.new_page()
    try:
        url = f"https://support.jamb.gov.ng/agent/candidates-tickets/show/{ticket_id}"
        await page.goto(url)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_selector(
            'h1:has-text("Ticket")', state="visible", timeout=60000
        )

        ticket_info = await extract_ticket_info(page)
        messages = await extract_messages(page, ticket_info.get("sender_name", ""))

        ticket_data = {**ticket_info, "messages": messages}

        # Log ticket data to console
        print(f"Ticket {ticket_id} data:")
        print(json.dumps(ticket_data, indent=2))

        return ticket_data
    except Exception as e:
        logger.error(f"Error processing ticket {ticket_id}: {str(e)}")
        return None
    finally:
        await page.close()


def check_last_reply(ticket_data):
    messages = ticket_data.get("messages", [])
    for message in reversed(messages):
        if validate_message(message):
            if "agent_name" in message:
                logger.info(
                    f"Ticket {ticket_data['ticket_id']}: Agent was last to reply"
                )
                logger.info(f"Last message: {json.dumps(message, indent=2)}")
                return ticket_data["ticket_id"]
            else:
                logger.info(
                    f"Ticket {ticket_data['ticket_id']}: Sender was last to reply"
                )
                logger.info(f"Last message: {json.dumps(message, indent=2)}")
                return None
    logger.warning(f"No valid messages found in ticket {ticket_data['ticket_id']}")
    return None


async def main():
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

                agent_last_reply_tickets = []
                total_processed = 0
                for ticket_id in ticket_ids:
                    ticket_data = await extract_ticket_data(context, ticket_id)
                    if ticket_data:
                        result = check_last_reply(ticket_data)
                        if result:
                            agent_last_reply_tickets.append(result)
                        total_processed += 1

                print("\nTicket IDs where agent was last to reply:")
                for ticket_id in agent_last_reply_tickets:
                    print(ticket_id)

                print(
                    f"\nTotal tickets where agent was last to reply: {len(agent_last_reply_tickets)}"
                )
                print(f"Total tickets processed: {total_processed}")

        except Exception as e:
            logger.error(f"An unexpected error occurred: {str(e)}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
