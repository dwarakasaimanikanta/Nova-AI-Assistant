"""
tests/test_google_workspace.py
------------------------------
Unit tests for the Google Workspace integration (Gmail, Calendar, Drive).
Fully mocked to allow headless execution without real credential files or network calls.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from tools.gmail_tool import GmailTool
from tools.calendar_tool import CalendarTool
from tools.drive_tool import DriveTool
from utils.google_auth import get_google_service


@pytest.fixture
def mock_google_service():
    """Patches get_google_service to return a double mock structure."""
    with patch("tools.gmail_tool.get_google_service") as mock_auth_gmail, \
         patch("tools.calendar_tool.get_google_service") as mock_auth_cal, \
         patch("tools.drive_tool.get_google_service") as mock_auth_drive:
         
        mock_client = MagicMock()
        mock_auth_gmail.return_value = mock_client
        mock_auth_cal.return_value = mock_client
        mock_auth_drive.return_value = mock_client
        yield mock_client


def test_gmail_tool_read_emails(mock_google_service) -> None:
    """Gmail: verify listing latest emails successfully reads and parses Inbox headers."""
    # Mock return list
    mock_google_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg123"}]
    }
    # Mock return detail
    mock_google_service.users().messages().get().execute.return_value = {
        "snippet": "Hello world snippet",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test Subject Line"},
                {"name": "From", "value": "test_sender@example.com"}
            ]
        }
    }

    tool = GmailTool()
    res = tool.execute(action="read_emails", max_results=1)

    assert "Latest Inbox messages:" in res
    assert "From: test_sender@example.com" in res
    assert "Subject: Test Subject Line" in res
    assert "Preview: Hello world snippet" in res


def test_gmail_tool_send_email(mock_google_service) -> None:
    """Gmail: verify send constructs base64 raw body and triggers messages.send."""
    mock_google_service.users().messages().send().execute.return_value = {"id": "sent999"}

    tool = GmailTool()
    res = tool.execute(
        action="send_email",
        recipient="boss@company.com",
        subject="Important Update",
        body="This is an urgent status update."
    )

    assert "Success" in res
    assert "Email sent successfully to boss@company.com" in res
    assert "sent999" in res
    mock_google_service.users().messages().send.assert_called_with(
        userId="me",
        body={"raw": "Q29udGVudC1UeXBlOiB0ZXh0L3BsYWluOyBjaGFyc2V0PSJ1cy1hc2NpaSIKTUlNRS1WZXJzaW9uOiAxLjAKQ29udGVudC1UcmFuc2Zlci1FbmNvZGluZzogN2JpdAp0bzogYm9zc0Bjb21wYW55LmNvbQpzdWJqZWN0OiBJbXBvcnRhbnQgVXBkYXRlCgpUaGlzIGlzIGFuIHVyZ2VudCBzdGF0dXMgdXBkYXRlLg=="}
    )


def test_gmail_tool_search_emails(mock_google_service) -> None:
    """Gmail: verify search returns matches for custom search queries."""
    mock_google_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg456"}]
    }
    mock_google_service.users().messages().get().execute.return_value = {
        "snippet": "Urgent review needed",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Q4 Budget Planning"},
                {"name": "From", "value": "manager@company.com"}
            ]
        }
    }

    tool = GmailTool()
    res = tool.execute(action="search_emails", query="subject:Budget", max_results=5)

    assert "Search results for 'subject:Budget':" in res
    assert "From: manager@company.com" in res
    assert "Urgent review needed" in res
    mock_google_service.users().messages().list.assert_called_with(
        userId="me", q="subject:Budget", maxResults=5
    )


def test_calendar_tool_list_events(mock_google_service) -> None:
    """Calendar: verify listing calendar items reads start/end datetimes."""
    mock_google_service.events().list().execute.return_value = {
        "items": [
            {
                "id": "evt101",
                "summary": "Engineering Standup",
                "start": {"dateTime": "2026-08-06T09:00:00Z"},
                "end": {"dateTime": "2026-08-06T09:30:00Z"}
            }
        ]
    }

    tool = CalendarTool()
    res = tool.execute(action="list_events")

    assert "Today's Calendar Schedule:" in res
    assert "Engineering Standup" in res
    assert "evt101" in res


def test_calendar_tool_create_event(mock_google_service) -> None:
    """Calendar: verify insert sends proper summary, start, and end parameters."""
    mock_google_service.events().insert().execute.return_value = {"id": "evt202"}

    tool = CalendarTool()
    res = tool.execute(
        action="create_event",
        summary="Lunch Meeting",
        start_time="2026-08-06T12:00:00Z",
        end_time="2026-08-06T13:00:00Z",
        description="Discuss roadmaps"
    )

    assert "Success" in res
    assert "Lunch Meeting" in res
    assert "evt202" in res
    mock_google_service.events().insert.assert_called_with(
        calendarId="primary",
        body={
            "summary": "Lunch Meeting",
            "description": "Discuss roadmaps",
            "start": {"dateTime": "2026-08-06T12:00:00Z", "timeZone": "UTC"},
            "end": {"dateTime": "2026-08-06T13:00:00Z", "timeZone": "UTC"}
        }
    )


def test_calendar_tool_delete_event(mock_google_service) -> None:
    """Calendar: verify event deletion invokes calendar.delete."""
    mock_google_service.events().delete().execute.return_value = {}

    tool = CalendarTool()
    res = tool.execute(action="delete_event", event_id="evt202")

    assert "Success" in res
    assert "evt202" in res
    mock_google_service.events().delete.assert_called_with(
        calendarId="primary", eventId="evt202"
    )


def test_drive_tool_list_files(mock_google_service) -> None:
    """Drive: verify listing files prints filenames and MIME types."""
    mock_google_service.files().list().execute.return_value = {
        "files": [
            {
                "id": "file303",
                "name": "Nova Spec.pdf",
                "mimeType": "application/pdf"
            }
        ]
    }

    tool = DriveTool()
    res = tool.execute(action="list_files", max_results=1)

    assert "Google Drive Files:" in res
    assert "Nova Spec.pdf" in res
    assert "application/pdf" in res


def test_drive_tool_search_files(mock_google_service) -> None:
    """Drive: verify searching files queries for partial filename matches."""
    mock_google_service.files().list().execute.return_value = {
        "files": [
            {
                "id": "file404",
                "name": "Nova Roadmap.docx",
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }
        ]
    }

    tool = DriveTool()
    res = tool.execute(action="search_files", query="Roadmap")

    assert "Search results for file query 'Roadmap':" in res
    assert "Nova Roadmap.docx" in res
    mock_google_service.files().list.assert_called_with(
        q="name contains 'Roadmap' and trashed = false",
        pageSize=10,
        fields="nextPageToken, files(id, name, mimeType)"
    )


def test_google_auth_test_redirection() -> None:
    """Auth: verify auth manager automatically yields mock when ENVIRONMENT=test is active."""
    # Ensure ENVIRONMENT == test is active
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        service = get_google_service("gmail", "v1")
        # Verify it returns a mock object, preventing auth execution
        assert isinstance(service, MagicMock)
