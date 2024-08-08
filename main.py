# main.py
import os
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from config import JSON_OUTPUT_DIR, MAX_PARALLEL_TABS, SAVE_INTERVAL
from login import login_to_support
from navigation import navigate_to_candidate_open_tickets_page
from extraction import extract_ticket_ids, process_ticket
from utils import save_to_json, ensure_directory_exists
from logger import StructuredLogger
from gemini_processor import (
    GeminiProcessor,
    AllAPIKeysExhaustedError,
    RateLimitExceededError,
)

logger = StructuredLogger(__name__)
load_dotenv()


async def process_tickets_with_gemini(tickets, processor):
    logger.info(f"Processing {len(tickets)} tickets with Gemini")
    try:
        processed_tickets = processor.process_tickets_batch(tickets)
        logger.info(f"Finished processing {len(processed_tickets)} tickets with Gemini")
        return processed_tickets
    except AllAPIKeysExhaustedError:
        logger.error("All API keys exhausted. Unable to process tickets.")
        return tickets
    except RateLimitExceededError:
        logger.warning("Rate limit exceeded. Waiting before retrying.")
        await asyncio.sleep(60)  # Wait for 1 minute before retrying
        return await process_tickets_with_gemini(tickets, processor)


async def main():
    ensure_directory_exists(JSON_OUTPUT_DIR)
    processed_tickets = []
    resume_from = 0

    progress_file = os.path.join(JSON_OUTPUT_DIR, "scraping_progress.json")
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            progress_data = json.load(f)
            processed_tickets = progress_data["processed_tickets"]
            resume_from = progress_data["next_ticket_index"]
        logger.info(f"Resuming from ticket index {resume_from}")

    try:
        processor = GeminiProcessor(env_file=".env")
    except ValueError as e:
        logger.error(f"Failed to initialize GeminiProcessor: {str(e)}")
        return

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
                    logger.info(f"Starting to process batch of {len(batch)} tickets")
                    tasks = [
                        process_ticket(context, ticket_id, processed_tickets)
                        for ticket_id in batch
                    ]
                    await asyncio.gather(*tasks)

                    logger.info(
                        f"Processed {i + len(batch)} out of {len(ticket_ids)} tickets"
                    )

                    processed_last_batch = await process_tickets_with_gemini(
                        processed_tickets[-len(batch) :], processor
                    )
                    processed_tickets[-len(batch) :] = processed_last_batch

                    for ticket in processed_last_batch:
                        logger.info(f"Processed ticket: {json.dumps(ticket, indent=2)}")

                    if (i + len(batch)) % SAVE_INTERVAL == 0:
                        save_to_json(processed_tickets)
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

                    logger.info(f"Finished processing batch of {len(batch)} tickets")

                remaining_tickets = len(processed_tickets) % MAX_PARALLEL_TABS
                if remaining_tickets > 0:
                    last_batch = processed_tickets[-remaining_tickets:]
                    processed_last_batch = await process_tickets_with_gemini(
                        last_batch, processor
                    )
                    processed_tickets[-remaining_tickets:] = processed_last_batch

                save_to_json(processed_tickets)
        except Exception as e:
            logger.error(f"An unexpected error occurred: {str(e)}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
