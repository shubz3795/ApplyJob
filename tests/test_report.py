import pytest
from src.reporter.report_generator import ReportGenerator

def test_report_generation():
    sample_jobs = [
        {
            "platform": "linkedin",
            "company": "Barclays",
            "title": "Senior SDET",
            "location": "Pune",
            "posted_date_str": "3h ago",
            "match_score": 95.5,
            "priority_tier": "🔥 HIGH PRIORITY",
            "salary": "38 LPA",
            "status": "applied",
            "url": "https://linkedin.com/jobs/view/111",
            "summary_reason": "Direct banking & C# Playwright match"
        },
        {
            "platform": "naukri",
            "company": "Startup",
            "title": "Junior QA",
            "location": "Noida",
            "posted_date_str": "12h ago",
            "match_score": 42.0,
            "priority_tier": "🔴 LOW MATCH",
            "salary": "8 LPA",
            "status": "skipped",
            "url": "https://naukri.com/job/222",
            "summary_reason": "Experience mismatch"
        }
    ]
    stats = {
        "linkedin_count": 1,
        "naukri_count": 1,
        "strong_matches": 1,
        "applied_count": 1,
        "skipped_count": 1,
        "best_paying": "Barclays (38 LPA)",
        "best_overall": "Senior SDET at Barclays (95.5%)"
    }
    gen = ReportGenerator(sample_jobs, stats)
    md = gen.generate_markdown()
    assert "Job Application Tracker" in md
    assert "Barclays" in md
    assert "95.5%" in md
    assert "APPLIED (DONE)" in md
    assert "EXCLUDED / SKIPPED" in md
    assert "Startup" in md
