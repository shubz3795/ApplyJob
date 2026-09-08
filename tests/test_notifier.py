import pytest
import json
from unittest.mock import patch, MagicMock
from io import BytesIO
from src.notifier.telegram_notifier import TelegramNotifier

@pytest.fixture
def tg_settings():
    return {
        "telegram": {
            "enabled": True,
            "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "chat_id": "-1001234567890",
            "notify_only_if_applied": False
        }
    }

def test_notifier_configuration(tg_settings):
    notifier = TelegramNotifier(tg_settings)
    assert notifier.is_configured() is True
    assert notifier.bot_token == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    assert notifier.chat_id == "-1001234567890"

def test_notifier_disabled():
    notifier = TelegramNotifier({"telegram": {"enabled": False}})
    assert notifier.is_configured() is False

def test_format_run_message(tg_settings):
    notifier = TelegramNotifier(tg_settings)
    run_meta = {
        "mode": "auto",
        "timestamp_str": "Sunday, 06 Sep 2026, 01:40 AM",
        "runtime_minutes": 3.5,
        "timed_out": False,
        "li_today": 2,
        "nk_today": 9
    }
    applied = [{
        "company": "Apexon",
        "title": "Senior SDET",
        "platform": "naukri",
        "location": "Pune",
        "match_score": 75.2,
        "url": "https://naukri.com/job/123"
    }]
    todo = [{
        "company": "RBS Lynk",
        "title": "Senior Automation Tester",
        "platform": "naukri",
        "location": "Pune",
        "match_score": 85.2,
        "url": "https://naukri.com/job/456"
    }]
    msg = notifier.format_run_message(run_meta, applied, todo)
    assert "Trigger type:</b> Easy Apply" in msg
    assert "Jobs applied in this run:</b> <b>1</b>" in msg
    assert "Applied from LinkedIn:</b> <b>0</b>" in msg
    assert "Applied from Naukri:</b> <b>1</b>" in msg
    assert "Apexon" in msg
    assert "RBS Lynk" in msg
    assert "75.2%" in msg
    assert "📍 Pune" in msg
    assert "LinkedIn:</b> 2 / 50" in msg
    assert "Top External Portal Roles" not in msg

def test_send_message_success(tg_settings):
    notifier = TelegramNotifier(tg_settings)
    mock_resp_data = json.dumps({"ok": True, "result": {"message_id": 999}}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_resp_data
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        success, msg = notifier.send_message("<b>Test Hello</b>")
        assert success is True
        assert "delivered successfully" in msg

def test_send_message_error(tg_settings):
    notifier = TelegramNotifier(tg_settings)
    mock_resp_data = json.dumps({"ok": False, "description": "Chat not found"}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_resp_data
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        success, msg = notifier.send_message("<b>Test Hello</b>")
        assert success is False
        assert "Chat not found" in msg

def test_chunking_long_message(tg_settings):
    notifier = TelegramNotifier(tg_settings)
    long_text = "Line\n" * 1500 # > 7000 chars
    chunks = notifier._chunk_message(long_text, max_len=3000)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 3000

def test_format_run_message_with_external_jobs(tg_settings):
    notifier = TelegramNotifier(tg_settings)
    run_meta = {"mode": "external", "trigger_type": "External Jobs", "timestamp_str": "Now", "runtime_minutes": 2.0}
    ext_jobs = [{
        "company": "Maersk",
        "title": "Automation Specialist",
        "platform": "linkedin",
        "location": "Pune",
        "match_score": 86.2,
        "url": "https://linkedin.com/job/789"
    }]
    msg = notifier.format_run_message(run_meta, [], [], external_jobs=ext_jobs)
    assert "Trigger type:</b> External Jobs" in msg
    assert "Top External Portal Roles" in msg
    assert "Maersk" in msg
    assert "86.2%" in msg
    assert "📍 Pune" in msg

def test_easy_apply_mode_suppresses_external_links(tg_settings):
    notifier = TelegramNotifier(tg_settings)
    run_meta = {"mode": "auto", "trigger_type": "Easy Apply", "timestamp_str": "Now", "runtime_minutes": 2.0}
    ext_jobs = [{
        "company": "Maersk",
        "title": "Automation Specialist",
        "platform": "linkedin",
        "location": "Pune",
        "match_score": 86.2,
        "url": "https://linkedin.com/job/789"
    }]
    msg = notifier.format_run_message(run_meta, [], [], external_jobs=ext_jobs)
    assert "Top External Portal Roles" not in msg
    assert "https://linkedin.com/job/789" not in msg

    # Also test send_run_summary ignores send_external_template when in Easy Apply mode
    with patch.object(notifier, "send_message", return_value=(True, "ok")) as mock_send:
        sent, _ = notifier.send_run_summary(
            run_meta,
            [],
            [],
            external_jobs=ext_jobs,
            send_external_template=True
        )
        assert sent is True
        # Only 1 message sent (summary), no second message with external cards!
        assert mock_send.call_count == 1
        summary_text = mock_send.call_args[0][0]
        assert "Top External Portal Roles" not in summary_text
        assert "Maersk" not in summary_text

def test_send_document_success(tg_settings, tmp_path):
    notifier = TelegramNotifier(tg_settings)
    test_file = tmp_path / "EXTERNAL_JOBS.md"
    test_file.write_text("# External Jobs Test", encoding="utf-8")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        success, msg = notifier.send_document(test_file, caption="Test Caption")
        assert success is True
        assert "delivered successfully" in msg
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["data"]["chat_id"] == "-1001234567890"
        assert call_kwargs["data"]["caption"] == "Test Caption"

def test_format_external_jobs_template(tg_settings):
    notifier = TelegramNotifier(tg_settings)
    jobs = [{
        "company": "Maersk",
        "title": "Automation Specialist",
        "location": "Pune",
        "match_score": 86.2,
        "url": "https://in.linkedin.com/jobs/view/123",
        "skip_reason": "C# SpecFlow match"
    }]
    card = notifier.format_external_jobs_template(jobs)
    assert "1-Click External Portal Roles" in card
    assert "Maersk" in card
    assert "86.2% Match" in card
    assert "Automation Specialist" in card
    assert "TAP TO APPLY ON MAERSK PORTAL" in card
    assert "https://in.linkedin.com/jobs/view/123" in card
