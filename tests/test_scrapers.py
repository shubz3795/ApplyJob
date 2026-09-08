import pytest
from src.scrapers.linkedin_scraper import LinkedInScraper
from src.scrapers.naukri_scraper import NaukriScraper

def test_linkedin_url_builder_default():
    scraper = LinkedInScraper()
    url = scraper.build_search_url("Senior SDET C#", location="India")
    assert "keywords=Senior%20SDET%20C%23" in url
    assert "location=India" in url
    assert "f_TPR=r86400" in url
    assert "f_AL=true" in url
    assert "sortBy=DD" in url

def test_linkedin_url_builder_multi_filters():
    custom_filters = {
        "freshness_hours": 48,
        "easy_apply_only": True,
        "under_10_applicants": True,
        "experience_levels": ["mid_senior"],
        "workplace_types": ["remote", "hybrid"],
        "job_types": ["full_time"],
        "sort_by_recent": True
    }
    scraper = LinkedInScraper(default_filters=custom_filters)
    url = scraper.build_search_url("Senior SDET")

    assert "f_TPR=r172800" in url
    assert "f_AL=true" in url
    assert "f_EA=true" in url
    assert "f_E=4" in url
    assert "f_WT=2%2C3" in url
    assert "f_JT=F" in url
    assert "sortBy=DD" in url

def test_linkedin_url_builder_include_external():
    scraper = LinkedInScraper(default_filters={"easy_apply_only": False})
    url = scraper.build_search_url("Senior SDET")
    assert "f_AL=true" not in url

def test_naukri_url_builder_default():
    scraper = NaukriScraper()
    url = scraper.build_search_url("Senior SDET C#")
    assert "k=Senior%20SDET%20C%23" in url
    assert "experience=8" in url
    assert "postDate=1" in url

def test_naukri_url_builder_multi_filters():
    custom_filters = {
        "experience_years": 9,
        "post_date_days": 3,
        "wfh_types": ["remote", "hybrid"]
    }
    scraper = NaukriScraper(default_filters=custom_filters)
    url = scraper.build_search_url("Senior SDET")
    assert "k=Senior%20SDET" in url
    assert "experience=9" in url
    assert "postDate=3" in url
    assert "wfhType=3,2" in url or "wfhType=2,3" in url
