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
