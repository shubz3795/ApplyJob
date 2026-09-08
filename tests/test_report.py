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

def test_run_report_generation(tmp_path):
    sample_jobs = [
        {
            "platform": "naukri",
            "company": "RBS Lynk",
            "title": "Senior SDET",
            "location": "Pune",
            "match_score": 85.2,
            "status": "discovered",
            "url": "https://naukri.com/123"
        }
    ]
    gen = ReportGenerator(sample_jobs, {})
    run_meta = {
        "mode": "auto",
        "runtime_minutes": 1.5,
        "timeout_minutes": 30.0,
        "timed_out": False,
        "discovered": 1,
        "li_today": 1,
        "nk_today": 2
    }
    applied = [{
        "time": "01:30 AM",
        "platform": "naukri",
        "company": "Apexon",
        "title": "Senior SDET",
        "location": "Pune",
        "match_score": 75.2,
        "outcome": "✅ Applied Successfully",
        "url": "https://naukri.com/456"
    }]
    report_file = gen.save_run_report(run_meta, applied, base_dir=tmp_path)
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "Apexon" in content
    assert "Applied Successfully" in content
    assert "Pune" in content

    recent = gen.get_recent_runs(base_dir=tmp_path)
    assert len(recent) == 1
    assert recent[0]["applied_count"] == 1
    assert recent[0]["mode"] == "auto"
