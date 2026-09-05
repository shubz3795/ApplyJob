import re
import time
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from playwright.sync_api import Page
from src.engine.screener import ScreeningEngine
from src.utils.logger import get_logger

logger = get_logger("NaukriApplier")

class NaukriApplier:
    """
    Automates Naukri Direct Apply flows safely.
    Handles Naukri questionnaires and detects external redirections.
    Strictly barred from profile edits, messages, or setting changes.
    """

    def __init__(self, screener: ScreeningEngine, review_mode: bool = True):
        self.screener = screener
        self.review_mode = review_mode

    def apply(self, page: Page, job: Dict[str, Any]) -> Tuple[bool, str]:
        url = job.get("url")
        if not url:
            return False, "Missing Job URL"

        # Strict Safety Invariant: NEVER navigate to profile edit, messages, settings, or payment
        if not re.search(r'naukri\.com/(?:job-listings|.*-jobs-)', url, re.IGNORECASE):
            logger.error(f"SAFETY GUARD TRIGGERED: Blocked non-job Naukri URL: {url}")
            return False, "Blocked by safety guard: Restricted strictly to Naukri job application pages"

        try:
            logger.info(f"Navigating to Naukri job: {job.get('title')} at {job.get('company')}")
            page.goto(url, timeout=35000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Check for Apply button
            apply_btn = page.query_selector("button#apply-button, button:has-text('Apply'), button:has-text('I am interested')")
            if not apply_btn:
                # Check for "Already Applied"
                if page.query_selector("span:has-text('Already Applied')"):
                    return True, "Already Applied on Naukri"
                return False, "Apply button not found (or external company site)"

            # Check if button text indicates external redirection
            btn_text = apply_btn.inner_text().strip().lower()
            if "company site" in btn_text or "external" in btn_text:
                return False, "Redirects to external company portal (Workday/ATS)"

            apply_btn.click()
            page.wait_for_timeout(2500)

            # Handle questionnaires / chips if any appear
            self._handle_naukri_questionnaire(page)

            # Check for confirmation
            if page.query_selector("span:has-text('Applied Successfully'), div:has-text('Application sent')"):
                return True, "Applied successfully on Naukri"

            return True, "Application initiated on Naukri"

        except Exception as e:
            return False, f"Exception during Naukri apply: {str(e)}"

    def _handle_naukri_questionnaire(self, page: Page):
        # Look for questionnaire modals or chatbot style prompts
        chips = page.query_selector_all("div.chip, button.chip")
        for chip in chips:
            try:
                txt = chip.inner_text().strip().lower()
                # If matches notice period (30 days) or CTC
                if "30" in txt or "1 month" in txt:
                    chip.click()
                    page.wait_for_timeout(500)
            except Exception:
                pass
