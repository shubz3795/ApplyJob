import pytest
from unittest.mock import MagicMock, patch
from src.notifier.telegram_listener import TelegramListener

@pytest.fixture
def mock_settings():
    return {
        "telegram": {
            "enabled": True,
            "bot_token": "fake_token_123",
            "chat_id": "-1004325484171"
        }
    }

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_all_jobs.return_value = [
        {
            "job_id": "j1",
            "platform": "naukri",
            "title": "Senior SDET C#",
            "company": "Nice Ltd",
            "location": "Pune",
            "match_score": 85.0,
            "status": "applied"
        },
        {
            "job_id": "j2",
            "platform": "linkedin",
            "title": "SDET Playwright",
            "company": "Fintech Co",
            "location": "Remote",
            "match_score": 80.0,
            "status": "discovered"
        }
    ]
    db.get_daily_applied_count.side_effect = lambda platform: 5 if platform == "linkedin" else 10
    return db

def test_listener_authorization(mock_settings, mock_db):
    listener = TelegramListener(mock_settings, mock_db, allowed_user_ids=[1181546323])
    
    # Authorized via channel chat_id
    assert listener.is_authorized("-1004325484171", user_id=None) is True
    # Authorized via user_id
    assert listener.is_authorized("random_chat", user_id=1181546323) is True
    # Unauthorized
    assert listener.is_authorized("random_chat", user_id=999999999) is False
    assert listener.is_authorized("other_channel", user_id=None) is False

def test_listener_help_command(mock_settings, mock_db):
    listener = TelegramListener(mock_settings, mock_db)
    with patch.object(listener.notifier, "send_message") as mock_send:
        listener.handle_command("/help", "-1004325484171")
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][0]
        assert "/run" in sent_text
        assert "/status" in sent_text
        assert "/apply" in sent_text

def test_listener_status_command(mock_settings, mock_db):
    listener = TelegramListener(mock_settings, mock_db)
    with patch.object(listener.notifier, "send_message") as mock_send:
        listener.handle_command("/status", "-1004325484171")
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][0]
        assert "Total Applied:" in sent_text
        assert "LinkedIn:</b> 5 / 50" in sent_text
        assert "Naukri:</b> 10 / 50" in sent_text
        assert "Pune" in sent_text or "Remote" in sent_text

def test_listener_run_auto_triggers_callback(mock_settings, mock_db):
    mock_run_cb = MagicMock()
    listener = TelegramListener(mock_settings, mock_db, run_agent_callback=mock_run_cb)
    
    with patch.object(listener.notifier, "send_message") as mock_send:
        listener.handle_command("/run", "-1004325484171")
        mock_send.assert_called_once()
        assert "Starting Autonomous Job Hunting Run" in mock_send.call_args[0][0]

def test_listener_lock_prevents_concurrent_runs(mock_settings, mock_db):
    listener = TelegramListener(mock_settings, mock_db)
    # Manually acquire the lock to simulate an ongoing run
    listener.is_running_lock.acquire()
    listener.current_task_info = {"active": True, "command": "/auto", "started_at": 1000.0}

    with patch.object(listener.notifier, "send_message") as mock_send:
        listener.handle_command("/run", "-1004325484171")
        mock_send.assert_called_once()
        assert "already active" in mock_send.call_args[0][0]

    listener.is_running_lock.release()

def test_listener_poll_updates_once(mock_settings, mock_db):
    listener = TelegramListener(mock_settings, mock_db)
    fake_updates = {
        "ok": True,
        "result": [
            {
                "update_id": 500,
                "channel_post": {
                    "chat": {"id": -1004325484171},
                    "text": "/status"
                }
            }
        ]
    }

    with patch("src.notifier.telegram_listener._make_request", return_value=fake_updates), \
         patch.object(listener, "handle_command") as mock_handle:
        listener.poll_updates_once()
        assert listener.last_update_id == 500
        mock_handle.assert_called_once_with("/status", "-1004325484171", sender_name="Channel Admin")

def test_listener_external_command(mock_settings, mock_db):
    listener = TelegramListener(mock_settings, mock_db)
    mock_db.get_all_jobs.return_value = [
        {
            "job_id": "ext1",
            "platform": "linkedin",
            "title": "Automation Specialist",
            "company": "Maersk",
            "location": "Pune",
            "match_score": 86.2,
            "status": "queued_external",
            "url": "https://linkedin.com/job/1"
        }
    ]

    with patch.object(listener.notifier, "send_message") as mock_send, \
         patch.object(listener.notifier, "send_document") as mock_doc:
        listener.handle_command("/external", "-1004325484171")
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][0]
        assert "Maersk" in sent_text
        assert "86.2%" in sent_text
        assert "Pune" in sent_text

def test_listener_mode_command(mock_settings, mock_db):
    listener = TelegramListener(mock_settings, mock_db)
    with patch.object(listener.notifier, "send_message") as mock_send, \
         patch("builtins.open", MagicMock()), \
         patch("yaml.dump", MagicMock()):
        # Query current mode
        listener.handle_command("/mode", "-1004325484171")
        mock_send.assert_called_once()
        assert "Current Application Mode" in mock_send.call_args[0][0]

        # Switch to easy mode
        mock_send.reset_mock()
        listener.handle_command("/mode easy", "-1004325484171")
        mock_send.assert_called_once()
        assert "Mode Switched: Easy Apply Only" in mock_send.call_args[0][0]
        assert listener.settings["search_filters"]["linkedin"]["easy_apply_only"] is True

        # Switch to external/hybrid mode
        mock_send.reset_mock()
        listener.handle_command("/mode external", "-1004325484171")
        mock_send.assert_called_once()
        assert "Mode Switched: Hybrid" in mock_send.call_args[0][0]
        assert listener.settings["search_filters"]["linkedin"]["easy_apply_only"] is False

def test_listener_run_with_mode_override(mock_settings, mock_db):
    listener = TelegramListener(mock_settings, mock_db)
    with patch.object(listener.notifier, "send_message") as mock_send, \
         patch("src.agent.autonomous_runner.AutonomousJobAgent") as mock_agent_cls:
        mock_agent_inst = MagicMock()
        mock_agent_cls.return_value = mock_agent_inst

        listener.handle_command("/run external", "-1004325484171")
        assert "Hybrid (Easy Apply + Queue External ATS)" in mock_send.call_args[0][0]

def test_listener_run_easy_apply_only(mock_settings, mock_db):
    listener = TelegramListener(mock_settings, mock_db)
    with patch.object(listener.notifier, "send_message") as mock_send, \
         patch("src.agent.autonomous_runner.AutonomousJobAgent") as mock_agent_cls:
        mock_agent_inst = MagicMock()
        mock_agent_cls.return_value = mock_agent_inst

        listener.handle_command("/run easy", "-1004325484171")
        assert "Easy Apply Only" in mock_send.call_args[0][0]

