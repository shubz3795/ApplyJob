import pytest
import yaml
from pathlib import Path
from src.engine.resume_parser import ResumeManager
from src.engine.screener import ScreeningEngine

@pytest.fixture
def screener(tmp_path):
    mgr = ResumeManager()
    base_dir = Path(__file__).resolve().parent.parent
    with open(base_dir / "config" / "settings.yaml") as f:
        settings = yaml.safe_load(f)
    bank_file = tmp_path / "test_bank.json"
    return ScreeningEngine(mgr.get_profile(), settings, bank_path=str(bank_file))

def test_screener_experience_questions(screener):
    ans, reason = screener.answer_question("What is your total professional IT experience?")
    assert ans == "9"
    assert "resume" in reason.lower()

    ans_csharp, _ = screener.answer_question("How many years of experience in C#?")
    assert ans_csharp == "9"

    ans_pw, _ = screener.answer_question("Hands-on experience with Playwright?")
    assert ans_pw == "4"

def test_screener_range_options(screener):
    options = ["0-3 years", "4-6 years", "7-9 years", "10+ years"]
    ans, _ = screener.answer_question("Total years of software testing experience?", options=options)
    assert ans == "7-9 years"

def test_screener_notice_period(screener):
    options = ["Immediate", "15 Days", "30 Days", "60 Days", "90 Days"]
    ans, _ = screener.answer_question("Official notice period?", options=options)
    assert ans == "30 Days"

def test_screener_zero_fabrication_unknown(screener):
    # An obscure skill not on resume
    ans, reason = screener.answer_question("Do you have 5 years experience in COBOL mainframe development?")
    assert ans is None
    assert "user confirmation" in reason.lower()
