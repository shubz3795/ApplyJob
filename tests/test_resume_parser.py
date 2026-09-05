import pytest
from pathlib import Path
from src.engine.resume_parser import ResumeManager

def test_resume_parser_loads_pdf():
    mgr = ResumeManager()
    text = mgr.get_raw_text()
    assert len(text) > 1000
    assert "SHUBHAM KULKARNI" in text.upper()
    assert "PLAYWRIGHT" in text.upper()
    assert "SELENIUM" in text.upper()

def test_resume_parser_profile_data():
    mgr = ResumeManager()
    profile = mgr.get_profile()
    assert profile["personal"]["full_name"] == "Shubham Kulkarni"
    assert profile["professional"]["total_experience_years"] == 9
    assert profile["skill_years"]["c#"] == 9
    assert profile["skill_years"]["playwright"] == 4
