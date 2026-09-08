import pytest
from src.storage.db import JobDatabase

@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_jobs.db"
    return JobDatabase(db_path=str(db_file))

def test_upsert_and_deduplication(test_db):
    job = {
        "platform": "linkedin",
        "title": "Senior SDET",
        "company": "TopBank",
        "location": "Pune",
        "url": "https://linkedin.com/jobs/view/9999",
        "hours_ago": 1.0,
        "salary": "35 LPA",
        "match_score": 92.0,
        "priority_tier": "🔥 HIGH PRIORITY"
    }
    job_id = test_db.upsert_job(job)
    assert job_id is not None
    assert test_db.is_job_seen(job_id) is True

    # Duplicate upsert should update, not throw
    test_db.upsert_job(job)
    all_jobs = test_db.get_all_jobs()
    assert len(all_jobs) == 1

def test_status_update(test_db):
    job = {
        "platform": "linkedin",
        "title": "Senior SDET",
        "company": "TopBank",
        "location": "Pune",
        "url": "https://linkedin.com/jobs/view/9999",
        "hours_ago": 1.0,
        "match_score": 90.0
    }
    job_id = test_db.upsert_job(job)
    test_db.mark_applied(job_id, status_msg="applied")
    all_jobs = test_db.get_all_jobs()
    assert all_jobs[0]["status"] == "applied"

def test_daily_applied_count_and_quotas(test_db):
    job1 = {
        "platform": "linkedin",
        "title": "Senior SDET",
        "company": "TopBank",
        "location": "Pune",
        "url": "https://linkedin.com/jobs/view/101",
        "match_score": 90.0
    }
    job2 = {
        "platform": "naukri",
        "title": "Senior SDET",
        "company": "TechCorp",
        "location": "Remote",
        "url": "https://naukri.com/jobs/view/102",
        "match_score": 92.0
    }
    id1 = test_db.upsert_job(job1)
    id2 = test_db.upsert_job(job2)
    test_db.mark_applied(id1, status_msg="applied")
    test_db.mark_applied(id2, status_msg="applied")

    assert test_db.get_daily_applied_count("linkedin") == 1
    assert test_db.get_daily_applied_count("naukri") == 1
    assert test_db.get_daily_applied_count("other") == 0

    stats = test_db.get_summary_stats()
    assert stats["linkedin_today"] == 1
    assert stats["naukri_today"] == 1
    assert stats["linkedin_limit"] == 50
    assert stats["naukri_limit"] == 50

def test_canonical_key_generation():
    # Suffixes, noise, and case should normalize to identical key
    key1 = JobDatabase.generate_canonical_key("Zensar Technologies Pvt Ltd", "Senior SDET (Playwright/C#) | Immediate Joiner", "Pune, Maharashtra")
    key2 = JobDatabase.generate_canonical_key("Zensar", "Senior SDET", "Pune")
    assert key1 == key2

    # Different roles or locations should have different keys
    key3 = JobDatabase.generate_canonical_key("Zensar", "Lead Java Developer", "Pune")
    key4 = JobDatabase.generate_canonical_key("Zensar", "Senior SDET", "Hyderabad")
    assert key1 != key3
    assert key1 != key4

def test_cross_platform_deduplication(test_db):
    li_job = {
        "platform": "linkedin",
        "title": "Senior SDET C#",
        "company": "Veeam Software India Pvt Ltd",
        "location": "Bengaluru, Karnataka",
        "url": "https://linkedin.com/jobs/view/111",
        "match_score": 95.0
    }
    nk_job = {
        "platform": "naukri",
        "title": "Senior SDET",
        "company": "Veeam Software",
        "location": "Bengaluru",
        "url": "https://naukri.com/job-listings-222",
        "match_score": 90.0
    }

    id_li = test_db.upsert_job(li_job)
    id_nk = test_db.upsert_job(nk_job)

    # Mark LinkedIn applied
    test_db.mark_applied(id_li, status_msg="applied")

    # Canonical key for Naukri job should report already applied!
    nk_ck = JobDatabase.generate_canonical_key(nk_job["company"], nk_job["title"], nk_job["location"])
    assert test_db.is_canonical_applied(nk_ck) is True

    applied_job = test_db.get_canonical_applied_job(nk_ck)
    assert applied_job is not None
    assert applied_job["platform"] == "linkedin"
    assert applied_job["company"] == "Veeam Software India Pvt Ltd"

