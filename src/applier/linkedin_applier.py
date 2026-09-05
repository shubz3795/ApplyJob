import re
import time
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from src.engine.screener import ScreeningEngine
from src.utils.logger import get_logger

logger = get_logger("LinkedInApplier")

class LinkedInApplier:
    """
    Production-grade LinkedIn Easy Apply automation.
    Handles Artdeco custom dropdowns, radio fieldsets, resume attachments,
    checkboxes, and human-in-the-loop review mode.
    """

    def __init__(self, screener: ScreeningEngine, resume_path: Optional[str] = None, review_mode: bool = True):
        self.screener = screener
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.resume_path = Path(resume_path) if resume_path else base_dir / "Shubham_Kulkarni_Resume.pdf"
        self.review_mode = review_mode

    def apply(self, page: Page, job: Dict[str, Any]) -> Tuple[bool, str]:
        url = job.get("url")
        if not url:
            return False, "Missing Job URL"

        # Strict Safety Invariant: NEVER navigate to feeds, messaging, profile edit, or posts
        if not re.search(r'linkedin\.com/jobs/(?:view|collections)', url, re.IGNORECASE):
            logger.error(f"SAFETY GUARD TRIGGERED: Blocked attempt to navigate to non-job URL: {url}")
            return False, "Blocked by safety guard: Restricted strictly to job application pages"

        title = job.get("title", "Job")
        company = job.get("company", "Company")

        try:
            logger.info(f"Navigating to: {title} at {company}")
            page.goto(url, timeout=35000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            # Check if already applied
            if page.query_selector("span:has-text('Applied'), button:has-text('Applied')"):
                logger.info(f"Already applied to {title} at {company}")
                return True, "Already applied"

            # Find Easy Apply button
            apply_btn = self._find_easy_apply_button(page)
            if not apply_btn:
                return False, "Not an Easy Apply job (requires external ATS redirect)"

            apply_btn.click()
            page.wait_for_timeout(2000)

            # Step through modal
            max_steps = 12
            step_count = 0

            while step_count < max_steps:
                step_count += 1
                page.wait_for_timeout(1500)

                # Check for submission success dialog
                if self._is_submitted(page):
                    logger.info(f"Successfully submitted application for {title} at {company}")
                    self._dismiss_modal(page)
                    return True, "Applied successfully"

                # Check if on final review step
                submit_btn = self._find_submit_button(page)
                if submit_btn and submit_btn.is_visible():
                    # Uncheck 'Follow company' if checked
                    self._uncheck_follow_company(page)

                    if self.review_mode:
                        print("\n" + "="*70)
                        print(f"⏸️  [HUMAN-IN-THE-LOOP REVIEW] Application ready for submission!")
                        print(f"   Role: {title} | Company: {company}")
                        print(f"   Match Score: {job.get('match_score', 0):.1f}%")
                        print("   Inspect the open browser window.")
                        print("   Press ENTER to submit, or type 's' to skip this application:")
                        user_choice = input("   > ").strip().lower()
                        if user_choice in ['s', 'skip', 'cancel', 'n', 'no']:
                            self._dismiss_modal(page)
                            return False, "Skipped by user in review mode"

                    submit_btn.click()
                    page.wait_for_timeout(3500)
                    self._dismiss_modal(page)
                    return True, "Applied successfully"

                # Fill all fields on active step
                self._fill_step_inputs(page)

                # Click Next or Review
                next_btn = self._find_next_button(page)
                if next_btn and next_btn.is_visible():
                    next_btn.click()
                    page.wait_for_timeout(1200)

                    # Check for inline validation errors
                    err = page.query_selector("div.jobs-easy-apply-modal .artdeco-inline-feedback--error")
                    if err and err.is_visible():
                        err_text = err.inner_text().strip()
                        logger.warning(f"Form validation issue: {err_text}")
                    continue

                review_btn = page.query_selector("button:has-text('Review'), button[aria-label='Review your application']")
                if review_btn and review_btn.is_visible():
                    review_btn.click()
                    continue

                break

            return False, "Reached step limit without reaching submission"

        except Exception as e:
            logger.error(f"Error applying to {title}: {e}")
            return False, f"Exception: {str(e)}"

    def _find_easy_apply_button(self, page: Page):
        selectors = [
            "button.jobs-apply-button:has-text('Easy Apply')",
            "div.jobs-apply-button--top-card button:has-text('Easy Apply')",
            "button[aria-label*='Easy Apply']",
            "button:has-text('Easy Apply')"
        ]
        for sel in selectors:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                return btn
        return None

    def _find_next_button(self, page: Page):
        selectors = [
            "button[aria-label='Continue to next step']",
            "button:has-text('Next')",
            "footer button:has-text('Next')"
        ]
        for sel in selectors:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                return btn
        return None

    def _find_submit_button(self, page: Page):
        selectors = [
            "button[aria-label='Submit application']",
            "button:has-text('Submit application')",
            "footer button:has-text('Submit application')"
        ]
        for sel in selectors:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                return btn
        return None

    def _is_submitted(self, page: Page) -> bool:
        indicators = [
            "h3:has-text('Application sent')",
            "div:has-text('Your application was sent to')",
            "span:has-text('Application submitted')"
        ]
        return any(bool(page.query_selector(ind)) for ind in indicators)

    def _fill_step_inputs(self, page: Page):
        modal = page.query_selector("div.jobs-easy-apply-modal")
        if not modal:
            return

        # 1. Resume File Upload
        file_input = modal.query_selector("input[type='file']")
        if file_input and self.resume_path.exists():
            try:
                # Check if resume is already attached
                uploaded = modal.query_selector(".jobs-document-upload__file-name, div[aria-label*='Resume']")
                if not uploaded:
                    file_input.set_input_files(str(self.resume_path))
                    page.wait_for_timeout(1500)
            except Exception as e:
                logger.debug(f"Resume upload: {e}")

        # 2. Text and Numeric Inputs
        inputs = modal.query_selector_all("input[type='text'], input[type='number']")
        for inp in inputs:
            try:
                if not inp.is_visible():
                    continue
                inp_id = inp.get_attribute("id") or ""
                label_text = self._get_label_for_input(page, inp, inp_id)
                curr_val = inp.input_value().strip()

                if not curr_val and label_text:
                    ans, reason = self.screener.answer_question(label_text, field_type="text")
                    if ans is not None:
                        inp.fill(ans)
                        logger.debug(f"Filled '{label_text}' with '{ans}' ({reason})")
                    else:
                        user_ans = self.screener.prompt_user_for_answer(label_text)
                        if user_ans:
                            inp.fill(user_ans)
            except Exception:
                pass

        # 3. Radio Fieldsets
        fieldsets = modal.query_selector_all("fieldset")
        for fs in fieldsets:
            try:
                legend = fs.query_selector("legend")
                if not legend:
                    continue
                q_text = legend.inner_text().strip()
                radios = fs.query_selector_all("input[type='radio']")
                options = []
                for r in radios:
                    r_id = r.get_attribute("id")
                    r_lbl = page.query_selector(f"label[for='{r_id}']")
                    if r_lbl:
                        options.append(r_lbl.inner_text().strip())

                ans, _ = self.screener.answer_question(q_text, field_type="radio", options=options)
                if ans:
                    for r in radios:
                        r_id = r.get_attribute("id")
                        r_lbl = page.query_selector(f"label[for='{r_id}']")
                        if r_lbl and ans.lower() in r_lbl.inner_text().strip().lower():
                            r_lbl.click()
                            break
            except Exception:
                pass

        # 4. Native & Artdeco Dropdowns
        selects = modal.query_selector_all("select")
        for sel in selects:
            try:
                sel_id = sel.get_attribute("id") or ""
                label_text = self._get_label_for_input(page, sel, sel_id)
                options = [opt.inner_text().strip() for opt in sel.query_selector_all("option") if opt.inner_text().strip()]
                ans, _ = self.screener.answer_question(label_text, field_type="dropdown", options=options)
                if ans:
                    sel.select_option(label=ans)
            except Exception:
                pass

    def _get_label_for_input(self, page: Page, elem, elem_id: str) -> str:
        if elem_id:
            lbl = page.query_selector(f"label[for='{elem_id}']")
            if lbl:
                return lbl.inner_text().strip()
        aria = elem.get_attribute("aria-label")
        if aria:
            return aria.strip()
        # Look for parent label
        parent = elem.evaluate_handle("el => el.closest('.fb-form-element, .jobs-easy-apply-form-section')")
        if parent:
            plbl = parent.as_element().query_selector(".fb-form-element-label, label")
            if plbl:
                return plbl.inner_text().strip()
        return ""

    def _uncheck_follow_company(self, page: Page):
        try:
            follow_cb = page.query_selector("input[id*='follow-company']")
            if follow_cb and follow_cb.is_checked():
                # Click label
                cb_id = follow_cb.get_attribute("id")
                lbl = page.query_selector(f"label[for='{cb_id}']")
                if lbl:
                    lbl.click()
        except Exception:
            pass

    def _dismiss_modal(self, page: Page):
        try:
            dismiss_btn = page.query_selector("button[aria-label='Dismiss']")
            if dismiss_btn:
                dismiss_btn.click()
                page.wait_for_timeout(800)
                discard_btn = page.query_selector("button:has-text('Discard')")
                if discard_btn:
                    discard_btn.click()
        except Exception:
            pass
