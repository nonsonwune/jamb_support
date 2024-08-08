import os
import csv
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import logging

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def login_to_support(playwright):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    try:
        # Navigate to the login page
        page.goto("https://support.jamb.gov.ng/login")

        # Wait for the page to load
        page.wait_for_load_state("domcontentloaded")

        # Wait for the email input to be visible
        page.wait_for_selector('input#email[type="email"]', state="visible")

        # Fill in the email and password
        page.fill('input#email[type="email"]', os.getenv("EMAIL"))
        page.fill('input#password[type="password"]', os.getenv("PASSWORD"))

        # Click the login button (assuming there's a submit button)
        page.click('button[type="submit"]')

        # Wait for navigation to complete
        page.wait_for_url("**/tickets**")

        # Log success
        logger.info("Login Successful")
        return page, context

    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        return None, None


def navigate_to_candidate_open_tickets_page(page, context):
    try:
        # Wait for the "Candidates Tickets" link to be visible and clickable
        candidates_tickets_link = page.wait_for_selector(
            'a#dashboard:has-text("Candidates Tickets")', state="visible"
        )

        # Click the link (which opens in a new tab)
        with context.expect_page() as new_page_info:
            candidates_tickets_link.click()
        new_page = new_page_info.value

        # Wait for the new page to load
        new_page.wait_for_load_state("domcontentloaded")

        # Wait for the "Ticket ID" header to be visible
        new_page.wait_for_selector('th:has-text("Ticket ID")', state="visible")

        logger.info("Candidates Ticket Page Successful")

        # Navigate to the specific URL
        new_page.goto("https://support.jamb.gov.ng/agent/candidates-tickets?s=1")

        # Wait for the URL to contain "?s=1"
        new_page.wait_for_url("**/candidates-tickets?s=1")

        logger.info("Navigating to Candidate Open Ticket Successful")

        return new_page
    except Exception as e:
        logger.error(f"Navigation failed: {str(e)}")
        return None


def extract_ticket_ids(page):
    try:
        # Wait for the table to load
        page.wait_for_selector("table#DataTables_Table_0")

        # Extract all Ticket IDs
        ticket_ids = page.eval_on_selector_all(
            "table#DataTables_Table_0 tbody tr td:first-child a",
            "elements => elements.map(el => el.textContent.trim())",
        )

        logger.info(f"Extracted {len(ticket_ids)} Ticket IDs")
        return ticket_ids
    except Exception as e:
        logger.error(f"Failed to extract Ticket IDs: {str(e)}")
        return []


def save_to_csv(ticket_ids, filename="ticket_ids.csv"):
    try:
        with open(filename, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["ticket_ids"])  # Write header
            for ticket_id in ticket_ids:
                writer.writerow([ticket_id])
        logger.info(f"Saved {len(ticket_ids)} Ticket IDs to {filename}")
    except Exception as e:
        logger.error(f"Failed to save Ticket IDs to CSV: {str(e)}")


def main():
    with sync_playwright() as playwright:
        page, context = login_to_support(playwright)
        if page and context:
            candidate_page = navigate_to_candidate_open_tickets_page(page, context)
            if candidate_page:
                ticket_ids = extract_ticket_ids(candidate_page)
                save_to_csv(ticket_ids)

            # Close the context after all operations are complete
            context.close()


if __name__ == "__main__":
    main()
