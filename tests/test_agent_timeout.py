import pytest
from unittest.mock import MagicMock, patch
from src.agent.autonomous_runner import AutonomousJobAgent
from src.storage.db import JobDatabase

@pytest.fixture
def mock_settings():
    return {
        "safety_guards": {
            "max_runtime_minutes": 30.0
        },
        "application_limits": {
            "daily_max_linkedin": 50,
            "daily_max_naukri": 50
        },
        "search_queries": {
            "linkedin": ["Senior SDET C#"],
            "naukri": ["Senior SDET C#"]
        }
    }

def test_agent_initializes_default_timeout(mock_settings, tmp_path):
    db_file = tmp_path / "test.db"
    db = JobDatabase(db_path=str(db_file))
    agent = AutonomousJobAgent(mock_settings, db=db)
    assert agent.max_runtime_minutes == 30.0

def test_agent_cycle_respects_timeout(mock_settings, tmp_path):
    db_file = tmp_path / "test.db"
    db = JobDatabase(db_path=str(db_file))
    agent = AutonomousJobAgent(mock_settings, db=db, base_dir=tmp_path)

    # When max_runtime_minutes is 0.0 (already expired), run_single_cycle should halt cleanly
    with patch("src.agent.autonomous_runner.LinkedInScraper") as mock_li:
        mock_scraper_inst = MagicMock()
        mock_li.return_value = mock_scraper_inst

        result = agent.run_single_cycle(min_score=75.0, search_limit=5, auto_apply=False, max_runtime_minutes=0.0)

        assert result["timed_out"] is True
        assert "runtime_seconds" in result
        # Scraper shouldn't have proceeded with search since timeout was already hit
        mock_scraper_inst.search_jobs.assert_not_called()
