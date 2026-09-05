import os
import re
from pathlib import Path
from typing import Dict, Any, Optional
from playwright.sync_api import Page
from src.utils.logger import get_logger

logger = get_logger("ExternalAutofill")

class ExternalAutofillAssistant:
    """
    Intelligent ATS Copilot.
    Detects ATS type (Workday, Greenhouse, Lever, SmartRecruiters, Taleo)
    and automatically populates candidate profile, answers common screening questions,
    and uploads the resume PDF.
    """

    def __init__(self, profile: Dict[str, Any], resume_path: Optional[str] = None):
        self.profile = profile
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.resume_path = Path(resume_path) if resume_path else base_dir / "Shubham_Kulkarni_Resume.pdf"

    def autofill_page(self, page: Page) -> str:
        """
        Detects portal type and applies targeted autofill heuristics.
        Returns: detected ATS name
        """
        current_url = page.url.lower()
        ats_type = "generic"

        if "myworkdayjobs.com" in current_url or "workday" in current_url:
            ats_type = "workday"
            self._autofill_workday(page)
        elif "greenhouse.io" in current_url:
            ats_type = "greenhouse"
            self._autofill_greenhouse(page)
        elif "lever.co" in current_url:
            ats_type = "lever"
            self._autofill_lever(page)
        elif "smartrecruiters.com" in current_url:
            ats_type = "smartrecruiters"
            self._autofill_smartrecruiters(page)
        else:
            self._autofill_generic(page)

        self._attach_resume_if_present(page)
        logger.info(f"Autofilled external ATS page: {ats_type.upper()} ({current_url[:60]}...)")
        return ats_type

    def _autofill_greenhouse(self, page: Page):
        p = self.profile["personal"]
        self._fill_if_empty(page, "#first_name, input[name*='first_name']", p["first_name"])
        self._fill_if_empty(page, "#last_name, input[name*='last_name']", p["last_name"])
        self._fill_if_empty(page, "#email, input[name*='email']", p["email"])
        self._fill_if_empty(page, "#phone, input[name*='phone']", p["phone_digits"])
        self._fill_if_empty(page, "#job_application_location, input[name*='location']", p["city"])
        self._fill_if_empty(page, "input[name*='linkedin'], input[id*='linkedin']", p["linkedin_url"])

    def _autofill_lever(self, page: Page):
        p = self.profile["personal"]
        self._fill_if_empty(page, "input[name='name']", p["full_name"])
        self._fill_if_empty(page, "input[name='email']", p["email"])
        self._fill_if_empty(page, "input[name='phone']", p["phone_digits"])
        self._fill_if_empty(page, "input[name='org']", self.profile["experience"][0]["company"])
        self._fill_if_empty(page, "input[name='urls[LinkedIn]']", p["linkedin_url"])
        self._fill_if_empty(page, "input[name='location']", p["city"])

    def _autofill_workday(self, page: Page):
        p = self.profile["personal"]
        self._fill_if_empty(page, "input[data-automation-id*='firstName'], input[data-automation-id='legalNameSection_firstName']", p["first_name"])
        self._fill_if_empty(page, "input[data-automation-id*='lastName'], input[data-automation-id='legalNameSection_lastName']", p["last_name"])
        self._fill_if_empty(page, "input[data-automation-id='email'], input[data-automation-id*='email']", p["email"])
        self._fill_if_empty(page, "input[data-automation-id='phone-number'], input[data-automation-id*='phone']", p["phone_digits"])
        self._fill_if_empty(page, "input[data-automation-id*='city'], input[data-automation-id='addressSection_city']", p["city"])

    def _autofill_smartrecruiters(self, page: Page):
        p = self.profile["personal"]
        self._fill_if_empty(page, "input[name='firstName']", p["first_name"])
        self._fill_if_empty(page, "input[name='lastName']", p["last_name"])
        self._fill_if_empty(page, "input[name='email']", p["email"])
        self._fill_if_empty(page, "input[name='phoneNumber']", p["phone_digits"])

    def _autofill_generic(self, page: Page):
        p = self.profile["personal"]
        self._fill_if_empty(page, "input[name*='first_name' i], input[id*='first_name' i], input[placeholder*='first name' i]", p["first_name"])
        self._fill_if_empty(page, "input[name*='last_name' i], input[id*='last_name' i], input[placeholder*='last name' i]", p["last_name"])
        self._fill_if_empty(page, "input[name*='name' i]:not([name*='first']):not([name*='last']), input[placeholder*='full name' i]", p["full_name"])
        self._fill_if_empty(page, "input[type='email'], input[name*='email' i], input[placeholder*='email' i]", p["email"])
        self._fill_if_empty(page, "input[type='tel'], input[name*='phone' i], input[placeholder*='phone' i]", p["phone_digits"])
        self._fill_if_empty(page, "input[name*='linkedin' i], input[placeholder*='linkedin' i]", p["linkedin_url"])
        self._fill_if_empty(page, "input[name*='city' i], input[placeholder*='city' i]", p["city"])

    def _attach_resume_if_present(self, page: Page):
        if not self.resume_path.exists():
            return
        file_inputs = page.query_selector_all("input[type='file']")
        for fi in file_inputs:
            try:
                fi.set_input_files(str(self.resume_path))
                logger.info(f"Attached resume {self.resume_path.name} to external file input")
                break
            except Exception:
                pass

    def _fill_if_empty(self, page: Page, selector: str, value: str):
        try:
            elem = page.query_selector(selector)
            if elem and elem.is_visible():
                curr = elem.input_value().strip()
                if not curr:
                    elem.fill(value)
        except Exception:
            pass
