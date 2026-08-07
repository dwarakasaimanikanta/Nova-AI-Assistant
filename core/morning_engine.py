"""
core/morning_engine.py
----------------------
Morning Intelligence Engine coordinating daily greetings, date/weekday info,
battery and network statuses, and provider interfaces (Weather, Calendar, Tasks, GitHub).
"""

import socket
import datetime
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Provider Interfaces ──────────────────────────────────────────────────────

class WeatherProvider(ABC):
    @abstractmethod
    def get_weather(self) -> str:
        pass


class CalendarProvider(ABC):
    @abstractmethod
    def get_events(self) -> List[str]:
        pass


class TaskProvider(ABC):
    @abstractmethod
    def get_tasks(self) -> List[str]:
        pass


class GitHubNotificationProvider(ABC):
    @abstractmethod
    def get_notifications(self) -> List[str]:
        pass


# ── Mock/Fallback Implementations ────────────────────────────────────────────

class MockWeatherProvider(WeatherProvider):
    def get_weather(self) -> str:
        return "Sunny, 24°C"


class MockCalendarProvider(CalendarProvider):
    def get_events(self) -> List[str]:
        return ["9:00 AM - Standup Meeting", "2:00 PM - Code Review Session"]


class MockTaskProvider(TaskProvider):
    def get_tasks(self) -> List[str]:
        return ["Complete Phase 2 design docs", "Review open PRs"]


class MockGitHubNotificationProvider(GitHubNotificationProvider):
    def get_notifications(self) -> List[str]:
        return ["PR #42 approved in Nova-AI-Assistant", "Issue #12 opened: Add test cases"]


# ── Morning Report Model ─────────────────────────────────────────────────────

class MorningReport:
    """Container representing the aggregated morning briefing details."""

    def __init__(
        self,
        greeting: str,
        date_str: str,
        weekday: str,
        battery: str,
        internet: str,
        weather: str,
        calendar_events: List[str],
        pending_tasks: List[str],
        github_notifications: List[str],
        recommendations: List[str],
        summary: str,
    ) -> None:
        self.greeting = greeting
        self.date = date_str
        self.weekday = weekday
        self.battery = battery
        self.internet = internet
        self.weather = weather
        self.calendar_events = calendar_events
        self.pending_tasks = pending_tasks
        self.github_notifications = github_notifications
        self.recommendations = recommendations
        self.summary = summary

    def to_dict(self) -> dict:
        return {
            "greeting": self.greeting,
            "date": self.date,
            "weekday": self.weekday,
            "battery": self.battery,
            "internet": self.internet,
            "weather": self.weather,
            "calendar_events": self.calendar_events,
            "pending_tasks": self.pending_tasks,
            "github_notifications": self.github_notifications,
            "recommendations": self.recommendations,
            "summary": self.summary,
        }


# ── Morning Engine Orchestrator ──────────────────────────────────────────────

class MorningEngine:
    """Orchestrates daily intelligence briefings using modular provider adapters."""

    def __init__(
        self,
        weather_provider: Optional[WeatherProvider] = None,
        calendar_provider: Optional[CalendarProvider] = None,
        task_provider: Optional[TaskProvider] = None,
        github_provider: Optional[GitHubNotificationProvider] = None,
    ) -> None:
        self.weather_provider = weather_provider or MockWeatherProvider()
        self.calendar_provider = calendar_provider or MockCalendarProvider()
        self.task_provider = task_provider or MockTaskProvider()
        self.github_provider = github_provider or MockGitHubNotificationProvider()

    def get_greeting(self, hour: Optional[int] = None) -> str:
        """Generate greeting based on the hour of local time."""
        if hour is None:
            hour = datetime.datetime.now().hour

        if hour < 12:
            return "Good morning"
        elif hour < 17:
            return "Good afternoon"
        elif hour < 22:
            return "Good evening"
        else:
            return "Good night"

    def check_internet(self) -> str:
        """Check internet connectivity by opening a socket test."""
        try:
            # 8.8.8.8 is Google DNS
            socket.setdefaulttimeout(1.0)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            return "Connected"
        except Exception:
            return "Disconnected"

    def check_battery(self) -> str:
        """Check battery status of the host machine."""
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery is None:
                return "Not Available"
            plugged = "Plugged In" if battery.power_plugged else "Discharging"
            return f"{battery.percent}% ({plugged})"
        except ImportError:
            return "Not Available"
        except Exception:
            return "Unknown"

    def generate_recommendations(self, tasks: List[str], weather: str) -> List[str]:
        """Generate recommendations based on tasks and weather conditions."""
        recs = []
        if tasks:
            recs.append(f"Prioritize task: '{tasks[0]}'")
        if "rain" in weather.lower():
            recs.append("It might rain today, keep an umbrella handy.")
        elif "sunny" in weather.lower():
            recs.append("Great sunny day! Stay hydrated.")
        return recs

    def build_summary(self, greeting: str, date: str, weather: str, events_count: int, tasks_count: int) -> str:
        """Compile a simple daily text summary."""
        return f"{greeting}! Today is {date}. Weather is {weather}. You have {events_count} events and {tasks_count} tasks scheduled."

    def generate_report(self) -> MorningReport:
        """Gathers data across all registered subsystems and compiles the final MorningReport."""
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        weekday = now.strftime("%A")

        greeting = self.get_greeting(now.hour)
        internet = self.check_internet()
        battery = self.check_battery()

        # Gather data from providers
        weather = self.weather_provider.get_weather()
        events = self.calendar_provider.get_events()
        tasks = self.task_provider.get_tasks()
        github = self.github_provider.get_notifications()

        recommendations = self.generate_recommendations(tasks, weather)
        summary = self.build_summary(greeting, weekday, weather, len(events), len(tasks))

        logger.info("[MorningEngine] Morning report generated successfully.")
        return MorningReport(
            greeting=greeting,
            date_str=date_str,
            weekday=weekday,
            battery=battery,
            internet=internet,
            weather=weather,
            calendar_events=events,
            pending_tasks=tasks,
            github_notifications=github,
            recommendations=recommendations,
            summary=summary,
        )
