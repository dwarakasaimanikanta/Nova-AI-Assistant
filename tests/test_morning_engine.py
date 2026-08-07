"""
tests/test_morning_engine.py
----------------------------
Unit tests verifying the MorningEngine briefing generation, provider mappings, and metrics.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.morning_engine import (
    MorningEngine, MorningReport, WeatherProvider, CalendarProvider,
    TaskProvider, GitHubNotificationProvider
)


class CustomWeather(WeatherProvider):
    def get_weather(self) -> str:
        return "Rainy, 15°C"


class CustomCalendar(CalendarProvider):
    def get_events(self) -> list[str]:
        return ["Meet team"]


class CustomTask(TaskProvider):
    def get_tasks(self) -> list[str]:
        return ["Write tests"]


class CustomGitHub(GitHubNotificationProvider):
    def get_notifications(self) -> list[str]:
        return ["PR feedback"]


def test_greeting_logic():
    """Verify time-of-day greeting mappings."""
    engine = MorningEngine()
    
    assert engine.get_greeting(hour=8) == "Good morning"
    assert engine.get_greeting(hour=13) == "Good afternoon"
    assert engine.get_greeting(hour=18) == "Good evening"
    assert engine.get_greeting(hour=23) == "Good night"


def test_recommendations():
    """Verify recommendation summaries are driven by active tasks and weather conditions."""
    engine = MorningEngine()
    
    # Sunny & Tasks
    recs1 = engine.generate_recommendations(["Task1"], "Sunny weather")
    assert "Prioritize task: 'Task1'" in recs1
    assert "Great sunny day! Stay hydrated." in recs1

    # Rain & No Tasks
    recs2 = engine.generate_recommendations([], "Heavy rain")
    assert len(recs2) == 1
    assert "It might rain today, keep an umbrella handy." in recs2


def test_internet_connectivity_check():
    """Verify check_internet maps connection failures and successes cleanly."""
    engine = MorningEngine()
    
    with patch("socket.socket") as mock_sock:
        # Mock successful connect
        assert engine.check_internet() == "Connected"

        # Mock exception
        mock_sock.side_effect = Exception("Network offline")
        assert engine.check_internet() == "Disconnected"


def test_battery_status_check():
    """Verify battery status checks recover gracefully if hardware is missing."""
    import sys
    engine = MorningEngine()
    mock_psutil = MagicMock()

    with patch.dict(sys.modules, {"psutil": mock_psutil}):
        # Case 1: Available and discharging
        mock_info = MagicMock()
        mock_info.percent = 85
        mock_info.power_plugged = False
        mock_psutil.sensors_battery.return_value = mock_info
        assert "85%" in engine.check_battery()
        assert "Discharging" in engine.check_battery()

        # Case 2: Not available
        mock_psutil.sensors_battery.return_value = None
        assert engine.check_battery() == "Not Available"


def test_custom_provider_injection():
    """Verify report collects data correctly from custom provider overrides."""
    engine = MorningEngine(
        weather_provider=CustomWeather(),
        calendar_provider=CustomCalendar(),
        task_provider=CustomTask(),
        github_provider=CustomGitHub()
    )

    report = engine.generate_report()
    assert report.weather == "Rainy, 15°C"
    assert report.calendar_events == ["Meet team"]
    assert report.pending_tasks == ["Write tests"]
    assert report.github_notifications == ["PR feedback"]
    assert "umbrella" in "".join(report.recommendations)

    data = report.to_dict()
    assert data["weather"] == "Rainy, 15°C"
    assert "date" in data
    assert "weekday" in data
