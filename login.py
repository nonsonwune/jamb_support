# login.py
import os
from logger import StructuredLogger

logger = StructuredLogger(__name__)


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
