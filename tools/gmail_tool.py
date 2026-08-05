"""
tools/gmail_tool.py
-------------------
Gmail integration tool supporting reading, sending, and searching emails.
Conforms to the BaseTool interface.
"""

import base64
from email.mime.text import MIMEText
from typing import Any
from tools.base_tool import BaseTool, RiskLevel
from utils.google_auth import get_google_service
from utils.logger import get_logger

logger = get_logger(__name__)


class GmailTool(BaseTool):
    """Unified Gmail tool to read, send, and search user emails."""

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def description(self) -> str:
        return (
            "Interacts with Gmail to read, send, and search emails. "
            "Supports action='read_emails' (optionally max_results), "
            "action='send_email' (requires recipient, subject, body), "
            "and action='search_emails' (requires query, optionally max_results)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read_emails", "send_email", "search_emails"],
                    "description": "The email action to execute.",
                },
                "recipient": {
                    "type": "string",
                    "description": "The destination email address (required for send_email).",
                },
                "subject": {
                    "type": "string",
                    "description": "The subject line of the email (required for send_email).",
                },
                "body": {
                    "type": "string",
                    "description": "The main message body of the email (required for send_email).",
                },
                "query": {
                    "type": "string",
                    "description": "Search query filter (required for search_emails, e.g. 'from:boss subject:urgent').",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of email threads to fetch (default: 5)."
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Sending email is a HIGH-risk action that will trigger confirmation gates.
        # Reading and searching are LOW-risk. We determine this dynamically in permission gate if needed,
        # but the tool's base risk level can be defined. Let's make it HIGH since it can send emails.
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: No action parameter provided."

        try:
            service = get_google_service("gmail", "v1")
        except Exception as e:
            logger.exception("Failed to connect to Google Auth/Gmail service: %s", e)
            return f"Failure: Google Authentication failed: {e}"

        if action == "read_emails":
            max_results = kwargs.get("max_results", 5)
            try:
                results = service.users().messages().list(userId="me", maxResults=max_results, labelIds=["INBOX"]).execute()
                messages = results.get("messages", [])
                if not messages:
                    return "No emails found in Inbox."

                lines = ["Latest Inbox messages:"]
                for msg in messages:
                    detail = service.users().messages().get(userId="me", id=msg["id"]).execute()
                    snippet = detail.get("snippet", "")
                    
                    # Extract headers
                    headers = detail.get("payload", {}).get("headers", [])
                    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
                    sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
                    
                    lines.append(f"- From: {sender} | Subject: {subject}\n  Preview: {snippet}")
                
                return "\n".join(lines)
            except Exception as e:
                logger.error("Gmail read error: %s", e)
                return f"Failure: Error reading emails: {e}"

        elif action == "send_email":
            recipient = kwargs.get("recipient")
            subject = kwargs.get("subject")
            body = kwargs.get("body")
            
            if not recipient or not subject or not body:
                return "Failure: Missing parameters. 'recipient', 'subject', and 'body' are all required for send_email."

            try:
                message = MIMEText(body)
                message["to"] = recipient
                message["subject"] = subject
                
                # Base64 urlsafe encoding
                raw_bytes = message.as_bytes()
                raw_base64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
                
                sent_msg = service.users().messages().send(userId="me", body={"raw": raw_base64}).execute()
                logger.info("Sent email to %s with ID %s", recipient, sent_msg.get("id"))
                return f"Success: Email sent successfully to {recipient} (ID: {sent_msg.get('id')})."
            except Exception as e:
                logger.error("Gmail send error: %s", e)
                return f"Failure: Error sending email: {e}"

        elif action == "search_emails":
            query = kwargs.get("query")
            if not query:
                return "Failure: Missing parameter. 'query' is required for search_emails."
            max_results = kwargs.get("max_results", 5)

            try:
                results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
                messages = results.get("messages", [])
                if not messages:
                    return f"No emails found matching query: '{query}'"

                lines = [f"Search results for '{query}':"]
                for msg in messages:
                    detail = service.users().messages().get(userId="me", id=msg["id"]).execute()
                    snippet = detail.get("snippet", "")
                    
                    # Extract headers
                    headers = detail.get("payload", {}).get("headers", [])
                    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
                    sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
                    
                    lines.append(f"- From: {sender} | Subject: {subject}\n  Preview: {snippet}")
                
                return "\n".join(lines)
            except Exception as e:
                logger.error("Gmail search error: %s", e)
                return f"Failure: Error searching emails: {e}"

        else:
            return f"Failure: Unsupported Gmail action '{action}'."
