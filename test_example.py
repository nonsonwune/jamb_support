import re
from playwright.sync_api import Page, expect


def test_has_title(page: Page):
    page.goto("https://support.jamb.gov.ng/login")

    # Expect a title "to contain" a substring.
    expect(page).to_have_title(re.compile("JAMB"))


def test_home_link(page: Page):
    page.goto("https://support.jamb.gov.ng/login")

    # Click the get started link.
    page.get_by_role("link", name="Home").click()

    # Expects page to have a heading with the name of Installation.
    expect(page.get_by_role("heading", name="Joint")).to_be_visible()
