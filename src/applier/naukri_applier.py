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

            # Check for Already Applied
            already_applied = page.query_selector(
                ".already-applied, [class*='already-applied'], span.already-applied, span:has-text('Applied'), button:has-text('Applied'), div:has-text('You have already applied')"
            )
            if already_applied:
                logger.info(f"Already applied to {job.get('title')} on Naukri.")
                return True, "Already Applied on Naukri"

            # Check if button indicates external redirection
            company_site_btn = page.query_selector(
                "button[class*='company-site-button'], button:has-text('Apply on company site'), a:has-text('Apply on company site'), button:has-text('Apply on Company Website')"
            )
            if company_site_btn:
                logger.info(f"Job redirects to external company portal: {job.get('title')} at {job.get('company')}")
                return False, "Redirects to external company portal (Workday/ATS)"

            # Check for Apply button (Naukri uses #apply-button, .styles_apply-button__uJI3A, or text matches)
            apply_btn = page.query_selector(
                "button#apply-button, button.styles_apply-button__uJI3A, button:has-text('Apply'), button:has-text('I am interested'), a#apply-button"
            )
            if not apply_btn:
                return False, "Apply button not found (or external company site)"

            # Check if button text indicates external redirection
            btn_text = apply_btn.inner_text().strip().lower()
            if "company site" in btn_text or "external" in btn_text:
                return False, "Redirects to external company portal (Workday/ATS)"

            if self.review_mode:
                print(f"\n[REVIEW MODE] Ready to apply to '{job.get('title')}' at '{job.get('company')}'.")
                confirm = input("Submit application? (y/n): ").strip().lower()
                if confirm not in ['y', 'yes']:
                    return False, "Skipped by user in review mode"

            apply_btn.click()
            page.wait_for_timeout(3000)

            # Handle questionnaires / chatbot if any appear
            self._handle_naukri_questionnaire(page)

            # Check for confirmation
            success_indicators = [
                "span:has-text('Applied Successfully')",
                "div:has-text('Application sent')",
                "div:has-text('successfully applied')",
                "span:has-text('Already applied')",
                "span:has-text('You have applied')"
            ]
            for selector in success_indicators:
                if page.query_selector(selector):
                    return True, "Applied successfully on Naukri"

            return True, "Application submitted on Naukri"

        except Exception as e:
            return False, f"Exception during Naukri apply: {str(e)}"

    def _handle_naukri_questionnaire(self, page: Page):
        """
        Handles interactive questionnaire modals / chatbots on Naukri.
        Strictly answers based on verified profile (Notice 30d, 9 YOE, CTC 27L/35L, Relocation Yes, Shifts Yes).
        Supports multi-turn questionnaires and chatbot flows.
        """
        for _ in range(4):
            try:
                # 1. Handle Notice Period chips / radios (30 days)
                chips = page.query_selector_all("div.chip, button.chip, span.chip, li.chip, div.radio-wrapper, label.radio, div.radioBtn, .chatbot-container button")
                for chip in chips:
                    try:
                        txt = chip.inner_text().strip().lower()
                        if any(p in txt for p in ["30 day", "1 month", "15 to 30", "15-30", "serving notice"]):
                            chip.click()
                            page.wait_for_timeout(300)
                        elif txt in ["yes", "willing", "agree", "comfortable", "open"]:
                            chip.click()
                            page.wait_for_timeout(300)
                        elif any(w in txt for w in ["relocate", "shift", "rotational", "flexible", "hybrid"]):
                            if "yes" in txt:
                                chip.click()
                                page.wait_for_timeout(300)
                    except Exception:
                        pass

                # 2. Select Yes on radio buttons for relocation, shifts, travel, or core skills
                radios = page.query_selector_all("input[type='radio']")
                for r in radios:
                    try:
                        val = (r.get_attribute("value") or "").lower()
                        r_id = r.get_attribute("id") or ""
                        lbl = page.query_selector(f"label[for='{r_id}']")
                        lbl_text = lbl.inner_text().strip().lower() if lbl else ""
                        if val in ["yes", "true", "y"] or "yes" in lbl_text:
                            if lbl and lbl.is_visible():
                                lbl.click()
                            else:
                                r.click()
                            page.wait_for_timeout(200)
                    except Exception:
                        pass

                # 3. Handle dropdowns (<select>) on Naukri
                selects = page.query_selector_all("select")
                for sel in selects:
                    try:
                        opts = [o.inner_text().strip() for o in sel.query_selector_all("option") if o.inner_text().strip()]
                        name = (sel.get_attribute("name") or "").lower()
                        id_attr = (sel.get_attribute("id") or "").lower()
                        parent = sel.evaluate_handle("el => el.closest('.form-group, .input-wrap, .field, div')")
                        lbl = parent.as_element().inner_text().lower() if parent else ""
                        ctx = f"{name} {id_attr} {lbl}"
                        if "notice" in ctx:
                            for opt in opts:
                                if any(k in opt.lower() for k in ["30", "1 month", "15 to 30", "15-30"]):
                                    sel.select_option(label=opt)
                                    break
                        elif any(w in ctx for w in ["experience", "exp", "years", "yoe"]):
                            for opt in opts:
                                if "9" in opt:
                                    sel.select_option(label=opt)
                                    break
                    except Exception:
                        pass

                # 4. Handle text/number input fields
                inputs = page.query_selector_all("input[type='text'], input[type='number'], textarea")
                for inp in inputs:
                    try:
                        if not inp.is_visible():
                            continue
                        placeholder = (inp.get_attribute("placeholder") or "").lower()
                        name = (inp.get_attribute("name") or "").lower()
                        label = ""
                        parent = inp.evaluate_handle("el => el.closest('.form-group, .input-wrap, .field, div')")
                        if parent:
                            try:
                                label = parent.as_element().inner_text().lower()
                            except Exception:
                                pass

                        context_str = f"{placeholder} {name} {label}"
                        val = inp.input_value().strip()
                        if not val:
                            tag_name = inp.evaluate("el => el.tagName.toLowerCase()")
                            maxlength_attr = inp.get_attribute("maxlength")
                            max_len = int(maxlength_attr) if maxlength_attr and maxlength_attr.isdigit() else None

                            if tag_name == "textarea" or any(w in context_str for w in ["fit", "cover letter", "message", "pitch", "why", "describe", "about yourself", "summary"]):
                                ans, _ = self.screener.answer_question(context_str, field_type="textarea", max_length=max_len)
                                if not ans:
                                    ans = self.screener.get_standard_pitch(max_length=max_len)
                                inp.fill(ans)
                            elif "current" in context_str and "ctc" in context_str:
                                inp.fill("27")
                            elif "expected" in context_str and "ctc" in context_str:
                                inp.fill("35")
                            elif "notice" in context_str:
                                inp.fill("30")
                            elif any(w in context_str for w in ["experience", "exp", "years", "tenure", "yoe"]):
                                inp.fill("9")
                        page.wait_for_timeout(200)
                    except Exception:
                        pass

                # 5. Look for Submit / Save / Next buttons inside questionnaire or chatbot
                submit_modal_btn = page.query_selector(
                    "button:has-text('Save and Apply'), button:has-text('Submit'), button:has-text('Save & Apply'), button:has-text('Apply Now'), button.submit-btn, button:has-text('Next'), .chatbot-container button:has-text('Send')"
                )
                if submit_modal_btn and submit_modal_btn.is_visible():
                    submit_modal_btn.click()
                    page.wait_for_timeout(1500)
                else:
                    break

            except Exception as e:
                logger.warning(f"Note on questionnaire handling: {e}")
                break

        # 6. Dismiss any post-application interstitial / upsell modals ("Similar Jobs", "FastForward")
        try:
            skip_btns = page.query_selector_all("span.crossIcon, button:has-text('Skip'), div.crossIcon, button[aria-label='Close'], .drawer-close")
            for sb in skip_btns:
                if sb.is_visible():
                    sb.click()
                    page.wait_for_timeout(500)
                    break
        except Exception:
            pass
