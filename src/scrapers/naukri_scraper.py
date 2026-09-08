import re
import time
from urllib.parse import quote
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from src.utils.logger import get_logger

logger = get_logger("NaukriScraper")

class NaukriScraper:
    """
    Resilient Naukri Scraper with Smooth Scrolling & Page Navigation.
    Filters strictly for postings within 24 hours (postDate=1 / f_TP=1).
    """

    BASE_SEARCH_URL = "https://www.naukri.com"

    WFH_TYPE_MAP = {
        "office": "0",
        "work_from_office": "0",
        "hybrid": "2",
        "remote": "3",
        "wfh": "3",
        "work_from_home": "3"
    }

    def __init__(self, browser_manager=None, default_filters: Optional[Dict[str, Any]] = None):
        self.browser_manager = browser_manager
        self.default_filters = default_filters or {}

    def build_search_url(
        self,
        query: str,
        experience_years: Optional[int] = None,
        post_date_days: Optional[int] = None,
        wfh_types: Optional[List[str]] = None,
        location: Optional[str] = None
    ) -> str:
        """
        Builds Naukri search URL with experience, freshness, and workplace filters.
        """
        slug = re.sub(r'[^a-zA-Z0-9]', '-', query).strip('-').lower()
        encoded_query = quote(query)
        base = f"{self.BASE_SEARCH_URL}/{slug}-jobs"

        exp = experience_years if experience_years is not None else self.default_filters.get("experience_years", 8)
        p_days = post_date_days if post_date_days is not None else self.default_filters.get("post_date_days", 1)

        params = [
            f"k={encoded_query}",
            f"experience={exp}",
            f"postDate={p_days}"
        ]

        wfh = wfh_types if wfh_types is not None else self.default_filters.get("wfh_types")
        if wfh:
            codes = [self.WFH_TYPE_MAP.get(str(x).lower(), str(x)) for x in wfh if str(x).lower() in self.WFH_TYPE_MAP or str(x).isdigit()]
            if codes:
                params.append(f"wfhType={','.join(codes)}")

        if location and location.lower() != "india":
            params.append(f"l={quote(location)}")

        return f"{base}?{'&'.join(params)}"

    def search_jobs(
        self,
        query: str,
        experience_years: Optional[int] = None,
        max_results: int = 20,
        post_date_days: Optional[int] = None,
        wfh_types: Optional[List[str]] = None,
        location: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        results = []
        if not self.browser_manager:
            from src.applier.browser_manager import BrowserManager
            self.browser_manager = BrowserManager(headless=False)

        page = self.browser_manager.new_page()
        try:
            search_url = self.build_search_url(
                query=query,
                experience_years=experience_years,
                post_date_days=post_date_days,
                wfh_types=wfh_types,
                location=location
            )
            
            logger.info(f"Navigating to Naukri search: '{query}' ({search_url})")
            page.goto(search_url, timeout=40000, wait_until="domcontentloaded")
            
            # Wait for content to render and trigger lazy load by scrolling
            page.wait_for_timeout(3000)
            self._scroll_down(page)

            content = page.content()
            soup = BeautifulSoup(content, "html.parser")
            
            cards = soup.find_all("div", class_=re.compile("srp-jobtuple-wrapper|jobTupleHeader"))
            if not cards:
                cards = soup.find_all("article", class_=re.compile("jobTuple"))

            logger.info(f"Found {len(cards)} job cards on Naukri page")

            for card in cards:
                job = self._parse_naukri_card(card)
                if job:
                    results.append(job)
                if len(results) >= max_results:
                    break

        except Exception as e:
            logger.error(f"Error querying Naukri for '{query}': {e}")
        finally:
            try:
                page.close()
            except Exception:
                pass

        return results

    def _scroll_down(self, page):
        """Scrolls down in increments to trigger lazy-loaded cards."""
        try:
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(800)
        except Exception:
            pass

    def _parse_naukri_card(self, card: BeautifulSoup) -> Optional[Dict[str, Any]]:
        title_tag = card.find("a", class_=re.compile("title"))
        comp_tag = card.find("a", class_=re.compile("comp-name")) or card.find("span", class_=re.compile("comp-name"))
        exp_tag = card.find("span", class_=re.compile("exp"))
        sal_tag = card.find("span", class_=re.compile("sal"))
        loc_tag = card.find("span", class_=re.compile("loc"))
        posted_tag = card.find("span", class_=re.compile("postedDate|fleft"))

        if not (title_tag and comp_tag):
            return None

        title = title_tag.get_text().strip()
        company = comp_tag.get_text().strip()
        url = title_tag.get("href", "")
        if url.startswith("/"):
            url = f"https://www.naukri.com{url}"

        exp_str = exp_tag.get_text().strip() if exp_tag else "7-10 Yrs"
        sal_str = sal_tag.get_text().strip() if sal_tag else "Not Disclosed"
        loc_str = loc_tag.get_text().strip() if loc_tag else "India"
        posted_str = posted_tag.get_text().strip() if posted_tag else "Today"

        hours_ago = self._parse_naukri_posted(posted_str)

        desc_tag = card.find("div", class_=re.compile("job-desc|ellipsis"))
        desc = desc_tag.get_text().strip() if desc_tag else ""

        tags = [t.get_text().strip() for t in card.find_all("li", class_=re.compile("dot"))]
        if tags:
            desc = f"{desc} | Skills: {', '.join(tags)}"

        job_id_match = re.search(r'-(\d+)(?:\?|$)', url)
        job_id = job_id_match.group(1) if job_id_match else None

        return {
            "platform": "naukri",
            "job_id": f"nk_{job_id}" if job_id else None,
            "title": title,
            "company": company,
            "location": loc_str,
            "url": url,
            "posted_date_str": posted_str,
            "hours_ago": hours_ago,
            "is_easy_apply": True,
            "salary": sal_str,
            "description": f"{title} at {company}. Experience: {exp_str}. Location: {loc_str}. Description: {desc}"
        }

    @staticmethod
    def _parse_naukri_posted(posted_str: str) -> float:
        s = posted_str.lower()
        if "just now" in s or "few hours" in s:
            return 2.0
        elif "today" in s or "1 day" in s:
            return 12.0
        elif "days ago" in s:
            nums = re.findall(r'\d+', s)
            days = float(nums[0]) if nums else 2.0
            return days * 24.0
        return 12.0
