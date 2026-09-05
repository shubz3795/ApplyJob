import pytest
from src.engine.resume_parser import ResumeManager
from src.engine.matcher import JobMatcher

@pytest.fixture
def matcher():
    mgr = ResumeManager()
    return JobMatcher(mgr.get_profile())

def test_high_priority_banking_sdet(matcher):
    job = {
        "title": "Senior SDET - C# Playwright Automation",
        "company": "Barclays",
        "description": "Seeking Senior SDET with 8-10 years experience in C#, Playwright, SpecFlow, BDD, RestSharp API testing, and Azure DevOps CI/CD for core banking.",
        "location": "Pune",
        "hours_ago": 3.0,
        "salary": "35-42 LPA"
    }
    result = matcher.evaluate(job)
    assert result["priority"] == "🔥 HIGH PRIORITY"
    assert result["total_score_pct"] >= 85.0
    assert result["action"] == "Apply"

def test_low_priority_mismatched_stack(matcher):
    job = {
        "title": "Junior QA Engineer (Python & Appium)",
        "company": "Local Agency",
        "description": "Requires 2 years experience in Python, Appium mobile automation, Jenkins. No C#.",
        "location": "Kolkata",
        "hours_ago": 40.0,
        "salary": "6-8 LPA"
    }
    result = matcher.evaluate(job)
    assert result["priority"] == "🔴 LOW MATCH"
    assert result["total_score_pct"] < 50.0
    assert result["action"] == "Skip"

def test_csharp_symbol_matching(matcher):
    # Tests that C# is not missed due to word boundaries
    job = {
        "title": "SDET (C# / Selenium)",
        "company": "MNC",
        "description": "Expert in C# and .NET unit testing.",
        "location": "Bengaluru",
        "hours_ago": 6.0
    }
    result = matcher.evaluate(job)
    assert "c#" in result["matched_skills"]
    assert ".net" in result["matched_skills"]
