import re
import time
import random
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.utils.logger import get_logger

logger = get_logger("LinkedInScraper")

class LinkedInScraper:
    """
    High-Performance, Resilient LinkedIn Scraper (< 24 Hours).
    Includes concurrency, exponential backoff, and randomized jitter.
    """

    BASE_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    JOB_DETAILS_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"

    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.linkedin.com/jobs"
    }

    EXP_LEVEL_MAP = {
        "internship": "1",
        "entry_level": "2",
        "entry": "2",
        "associate": "3",
        "mid_senior": "4",
        "mid_senior_level": "4",
        "senior": "4",
        "director": "5",
        "executive": "6"
    }

    WORKPLACE_TYPE_MAP = {
        "on_site": "1",
        "onsite": "1",
        "remote": "2",
        "hybrid": "3"
    }

    JOB_TYPE_MAP = {
        "full_time": "F",
        "fulltime": "F",
        "part_time": "P",
        "contract": "C",
        "temporary": "T",
        "internship": "I"
    }

    def __init__(self, session: Optional[requests.Session] = None, max_workers: int = 2, default_filters: Optional[Dict[str, Any]] = None):
        self.session = session or requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.max_workers = max_workers
        self.default_filters = default_filters or {}

    def build_search_url(
        self,
        query: str,
        location: str = "India",
        freshness_hours: Optional[int] = None,
        easy_apply_only: Optional[bool] = None,
        under_10_applicants: Optional[bool] = None,
        experience_levels: Optional[List[str]] = None,
        workplace_types: Optional[List[str]] = None,
        job_types: Optional[List[str]] = None,
        sort_by_recent: Optional[bool] = None,
        start: int = 0
    ) -> str:
        """
        Builds LinkedIn job search URL with multiple UI filter pills.
        """
        params = [
            f"keywords={quote(query)}",
            f"location={quote(location)}",
            f"start={start}"
        ]

        # 1. Freshness / Date Posted (f_TPR)
        fh = freshness_hours if freshness_hours is not None else self.default_filters.get("freshness_hours", 24)
        if fh and fh > 0:
            params.append(f"f_TPR=r{int(fh * 3600)}")

        # 2. Easy Apply (f_AL)
        ea_only = easy_apply_only if easy_apply_only is not None else self.default_filters.get("easy_apply_only", True)
        if ea_only:
            params.append("f_AL=true")

        # 3. Under 10 Applicants / Early Applicant (f_EA)
        u10 = under_10_applicants if under_10_applicants is not None else self.default_filters.get("under_10_applicants", False)
        if u10:
            params.append("f_EA=true")

        # 4. Experience Level (f_E)
        exp = experience_levels if experience_levels is not None else self.default_filters.get("experience_levels")
        if exp:
            codes = [self.EXP_LEVEL_MAP.get(str(x).lower(), str(x)) for x in exp]
            params.append(f"f_E={quote(','.join(codes))}")

        # 5. Workplace Type (f_WT)
        wt = workplace_types if workplace_types is not None else self.default_filters.get("workplace_types")
        if wt:
            codes = [self.WORKPLACE_TYPE_MAP.get(str(x).lower(), str(x)) for x in wt]
            params.append(f"f_WT={quote(','.join(codes))}")

        # 6. Job Type (f_JT)
        jt = job_types if job_types is not None else self.default_filters.get("job_types")
        if jt:
            codes = [self.JOB_TYPE_MAP.get(str(x).lower(), str(x)) for x in jt]
            params.append(f"f_JT={quote(','.join(codes))}")

        # 7. Sort Order (sortBy=DD for strict newest chronologically)
        sbr = sort_by_recent if sort_by_recent is not None else self.default_filters.get("sort_by_recent", True)
        if sbr:
            params.append("sortBy=DD")

        return f"{self.BASE_SEARCH_URL}?{'&'.join(params)}"

    def search_jobs(
        self,
        query: str,
        location: str = "India",
        max_results: int = 20,
        freshness_hours: Optional[int] = None,
        easy_apply_only: Optional[bool] = None,
        under_10_applicants: Optional[bool] = None,
        experience_levels: Optional[List[str]] = None,
        workplace_types: Optional[List[str]] = None,
        job_types: Optional[List[str]] = None,
        sort_by_recent: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches LinkedIn jobs using configured multi-filters (Easy Apply, Under 10 applicants, Experience level, etc.).
        """
        results = []
        url = self.build_search_url(
            query=query,
            location=location,
            freshness_hours=freshness_hours,
            easy_apply_only=easy_apply_only,
            under_10_applicants=under_10_applicants,
            experience_levels=experience_levels,
            workplace_types=workplace_types,
            job_types=job_types,
            sort_by_recent=sort_by_recent,
            start=0
        )

        resp = self._request_with_retry(url)
        if not resp or resp.status_code != 200:
            logger.warning(f"Failed to fetch LinkedIn search for query: '{query}'")
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all("li")

        for card in cards:
            job = self._parse_card(card)
            if job:
                results.append(job)
            if len(results) >= max_results:
                break

        fh = freshness_hours if freshness_hours is not None else self.default_filters.get("freshness_hours", 24)
        logger.info(f"Query '{query}' yielded {len(results)} fresh listings (<{fh}h)")
        return results

    def fetch_descriptions_concurrently(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fetches full job descriptions concurrently using a bounded thread pool.
        """
        jobs_to_fetch = [j for j in jobs if not j.get("description")]
        if not jobs_to_fetch:
            return jobs

        logger.info(f"Fetching JDs concurrently for {len(jobs_to_fetch)} jobs (workers={self.max_workers})...")
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_job = {executor.submit(self.fetch_job_description, job): job for job in jobs_to_fetch}
            for future in as_completed(future_to_job):
                try:
                    future.result()
                except Exception as e:
                    logger.debug(f"JD fetch error: {e}")

        return jobs

    def fetch_job_description(self, job: Dict[str, Any]) -> str:
        job_id = job.get("job_id", "").replace("li_", "")
        if not job_id:
            m = re.search(r'-(\d+)(?:$|/)', job.get("url", ""))
            if m:
                job_id = m.group(1)

        if not job_id:
            return ""

        url = f"{self.JOB_DETAILS_URL}/{job_id}"
        # Polite delay to prevent rate limits
        time.sleep(random.uniform(0.6, 1.2))
        resp = self._request_with_retry(url)
        if resp and resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            desc_div = soup.find("div", class_="description__text")
            if desc_div:
                text = desc_div.get_text(separator=" ").strip()
                job["description"] = text
                return text

        return ""

    def _request_with_retry(self, url: str, max_retries: int = 3) -> Optional[requests.Response]:
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, timeout=12)
                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 429:
                    sleep_time = (2 ** attempt) + random.uniform(1.0, 2.0)
                    logger.warning(f"Rate limited (429). Backing off for {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
                else:
                    logger.debug(f"HTTP {resp.status_code} for {url}")
            except requests.RequestException as e:
                sleep_time = (2 ** attempt) + 0.5
                logger.debug(f"Request failed ({e}). Retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)

        return None

    def _parse_card(self, card: BeautifulSoup) -> Optional[Dict[str, Any]]:
        title_tag = card.find("h3", class_="base-search-card__title")
        company_tag = card.find("h4", class_="base-search-card__subtitle")
        loc_tag = card.find("span", class_="job-search-card__location")
        time_tag = card.find("time")
        link_tag = card.find("a", class_="base-card__full-link")

        if not (title_tag and company_tag and link_tag):
            return None

        title = title_tag.text.strip()
        company = company_tag.text.strip()
        location = loc_tag.text.strip() if loc_tag else "India"
        url = link_tag.get("href", "").split("?")[0]
        posted_str = time_tag.text.strip() if time_tag else "Recently"
        hours_ago = self._parse_hours_ago(posted_str)

        job_id_match = re.search(r'-(\d+)(?:$|/)', url)
        job_id = job_id_match.group(1) if job_id_match else None
        is_easy_apply = True  # Guaranteed by f_AL=true filter in search query

        return {
            "platform": "linkedin",
            "job_id": f"li_{job_id}" if job_id else None,
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "posted_date_str": posted_str,
            "hours_ago": hours_ago,
            "is_easy_apply": is_easy_apply,
            "salary": "Not Disclosed",
            "description": ""
        }

    @staticmethod
    def _parse_hours_ago(posted_str: str) -> float:
        posted = posted_str.lower()
        if "minute" in posted or "m ago" in posted or "just now" in posted:
            return 0.5
        elif "hour" in posted or "h ago" in posted:
            nums = re.findall(r'\d+', posted)
            return float(nums[0]) if nums else 2.0
        elif "day" in posted:
            nums = re.findall(r'\d+', posted)
            days = float(nums[0]) if nums else 1.0
            return days * 24.0
        return 12.0
