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

def test_screener_relocation_and_shifts(screener):
    # Relocation
    ans_reloc, _ = screener.answer_question("Are you willing to relocate to Pune or other locations?")
    assert ans_reloc == "Yes"

    ans_reloc_opt, _ = screener.answer_question("Are you open to relocation?", options=["Yes", "No"])
    assert ans_reloc_opt == "Yes"

    # Shift Timings
    ans_shift, _ = screener.answer_question("Are you comfortable working in rotational shift timings or US shift?")
    assert ans_shift == "Yes"

    ans_shift_opt, _ = screener.answer_question("Willing to work in rotational shifts?", options=["Yes", "No"])
    assert ans_shift_opt == "Yes"

def test_screener_generic_experience(screener):
    ans_automation, _ = screener.answer_question("How many years of work experience do you have with Test Automation?")
    assert ans_automation == "9"

    ans_gen, _ = screener.answer_question("How many years of relevant experience do you have?")
    assert ans_gen == "9"

    ans_selenium, _ = screener.answer_question("Years of experience in Selenium WebDriver?")
    assert ans_selenium == "8"

def test_screener_binary_yes_no(screener):
    # Core skills -> Yes
    ans_csharp, _ = screener.answer_question("Do you have hands-on experience with C#?", options=["Yes", "No"])
    assert ans_csharp == "Yes"

    ans_pw, _ = screener.answer_question("Are you proficient in Playwright automation framework?", options=["Yes", "No"])
    assert ans_pw == "Yes"

    # Sponsorship -> No
    ans_spons, _ = screener.answer_question("Will you now or in the future require visa sponsorship?", options=["Yes", "No"])
    assert ans_spons == "No"

    # Work Authorization -> Yes
    ans_auth, _ = screener.answer_question("Are you legally authorized to work in India?", options=["Yes", "No"])
    assert ans_auth == "Yes"

def test_screener_summary(screener):
    ans_sum, _ = screener.answer_question("Please provide a brief professional summary of yourself.")
    assert ans_sum is not None
    assert "Senior Automation Engineer" in ans_sum or "9 years" in ans_sum or "Senior SDET" in ans_sum

def test_screener_good_fit_and_message_box(screener):
    # The exact LinkedIn Easy Apply user prompt
    ans_fit, reason = screener.answer_question("describe in short why it good fit for you")
    assert ans_fit is not None
    assert "Senior SDET" in ans_fit
    assert "9 years" in ans_fit
    assert "Playwright" in ans_fit
    assert "Pune" in ans_fit
    assert "30 days" in ans_fit

    # Message to hiring team prompt
    ans_msg, _ = screener.answer_question("Include a message to the hiring team")
    assert ans_msg is not None
    assert "Senior SDET" in ans_msg

    # Note to hiring manager
    ans_note, _ = screener.answer_question("Add a note to the hiring manager explaining why you are a fit")
    assert ans_note is not None
    assert "Senior SDET" in ans_note

    # Why should we hire you
    ans_why, _ = screener.answer_question("Why should we hire you for this Senior SDET role?")
    assert ans_why is not None
    assert "Senior SDET" in ans_why

def test_screener_pitch_character_limits(screener):
    # Standard pitch without max_length
    full = screener.get_standard_pitch()
    assert len(full) > 200

    # Concise pitch when constrained by textarea maxlength (e.g. 150 chars)
    short = screener.get_standard_pitch(max_length=150)
    assert len(short) <= 150
    assert "Senior SDET" in short
    assert "Pune" in short

