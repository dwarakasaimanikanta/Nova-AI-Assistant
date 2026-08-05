"""
tools/calendar_tool.py
----------------------
Google Calendar integration tool supporting listing today's events, creating events, and deleting events.
Conforms to the BaseTool interface.
"""

import datetime
from typing import Any
from tools.base_tool import BaseTool, RiskLevel
from utils.google_auth import get_google_service
from utils.logger import get_logger

logger = get_logger(__name__)


class CalendarTool(BaseTool):
    """Google Calendar tool to manage events."""

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return (
            "Manages Google Calendar events. "
            "Supports action='list_events' (today's schedule), "
            "action='create_event' (requires summary, start_time, end_time, optional description), "
            "and action='delete_event' (requires event_id)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_events", "create_event", "delete_event"],
                    "description": "Calendar operation to perform.",
                },
                "summary": {
                    "type": "string",
                    "description": "Event title/summary (required for create_event).",
                },
                "start_time": {
                    "type": "string",
                    "description": "ISO 8601 string representation of start datetime (required for create_event, e.g. '2026-08-06T15:00:00Z').",
                },
                "end_time": {
                    "type": "string",
                    "description": "ISO 8601 string representation of end datetime (required for create_event, e.g. '2026-08-06T16:00:00Z').",
                },
                "description": {
                    "type": "string",
                    "description": "Optional notes/details of the event.",
                },
                "event_id": {
                    "type": "string",
                    "description": "Google Calendar event identifier (required for delete_event).",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Creating or deleting calendar events can be HIGH-risk. Listing is LOW.
        # We defaults to HIGH since it has write capabilities.
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: No action parameter provided."

        try:
            service = get_google_service("calendar", "v3")
        except Exception as e:
            logger.exception("Failed to connect to Google Auth/Calendar service: %s", e)
            return f"Failure: Google Authentication failed: {e}"

        if action == "list_events":
            try:
                # Range: start of today to end of today
                now = datetime.datetime.now(datetime.timezone.utc)
                start_of_today = datetime.datetime(now.year, now.month, now.day, tzinfo=datetime.timezone.utc).isoformat()
                end_of_today = (datetime.datetime(now.year, now.month, now.day, tzinfo=datetime.timezone.utc) + datetime.timedelta(days=1)).isoformat()

                events_result = service.events().list(
                    calendarId="primary",
                    timeMin=start_of_today,
                    timeMax=end_of_today,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
                events = events_result.get("items", [])

                if not events:
                    return "No events found scheduled for today."

                lines = ["Today's Calendar Schedule:"]
                for event in events:
                    start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "")
                    end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date", "")
                    summary = event.get("summary", "(No Title)")
                    event_id = event.get("id")
                    lines.append(f"- {summary}\n  Start: {start} | End: {end}\n  ID: {event_id}")

                return "\n".join(lines)
            except Exception as e:
                logger.error("Calendar list error: %s", e)
                return f"Failure: Error listing events: {e}"

        elif action == "create_event":
            summary = kwargs.get("summary")
            start_time = kwargs.get("start_time")
            end_time = kwargs.get("end_time")
            description = kwargs.get("description", "")

            if not summary or not start_time or not end_time:
                return "Failure: Missing parameters. 'summary', 'start_time', and 'end_time' are all required for create_event."

            try:
                event_body = {
                    "summary": summary,
                    "description": description,
                    "start": {
                        "dateTime": start_time,
                        "timeZone": "UTC",
                    },
                    "end": {
                        "dateTime": end_time,
                        "timeZone": "UTC",
                    },
                }

                created_event = service.events().insert(calendarId="primary", body=event_body).execute()
                logger.info("Created calendar event '%s' with ID %s", summary, created_event.get("id"))
                return (
                    f"Success: Event '{summary}' created successfully.\n"
                    f"Start: {start_time} | End: {end_time}\n"
                    f"Event ID: {created_event.get('id')}"
                )
            except Exception as e:
                logger.error("Calendar create error: %s", e)
                return f"Failure: Error creating calendar event: {e}"

        elif action == "delete_event":
            event_id = kwargs.get("event_id")
            if not event_id:
                return "Failure: Missing parameter. 'event_id' is required for delete_event."

            try:
                service.events().delete(calendarId="primary", eventId=event_id).execute()
                logger.info("Deleted calendar event with ID %s", event_id)
                return f"Success: Calendar event with ID '{event_id}' has been deleted."
            except Exception as e:
                logger.error("Calendar delete error for ID %s: %s", event_id, e)
                return f"Failure: Error deleting calendar event: {e}"

        else:
            return f"Failure: Unsupported Calendar action '{action}'."
