"""
tools/android_tool.py
---------------------
Android phone integration via ADB (Android Debug Bridge).
Supports: calls, SMS, WhatsApp messages, reading notifications, reading contacts.
Requires ADB installed and USB debugging enabled on the Android device.
Conforms to the BaseTool interface.
"""

import json
import subprocess
from pathlib import Path
from typing import Any

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)

# Path to local contacts file for name→phone resolution
CONTACTS_FILE = Path(__file__).parent.parent / "data" / "contacts.json"


def _run_adb(args: list[str], timeout: int = 10) -> tuple[bool, str]:
    """Run an adb command, return (success, output)."""
    try:
        result = subprocess.run(
            ["adb"] + args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip() or result.stdout.strip()
    except FileNotFoundError:
        return False, "ADB not found. Please install Android Debug Bridge."
    except subprocess.TimeoutExpired:
        return False, "ADB command timed out."
    except Exception as e:
        return False, str(e)


def _load_contacts() -> dict[str, str]:
    """Load contacts from local JSON file. Returns {name_lower: phone_number}."""
    if not CONTACTS_FILE.exists():
        return {}
    try:
        with open(CONTACTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {k.lower(): v for k, v in data.items()}
    except Exception as e:
        logger.warning("Failed to load contacts file: %s", e)
        return {}


def _resolve_contact(name: str) -> str | None:
    """Resolve a contact name to a phone number. Returns number or None."""
    contacts = _load_contacts()
    return contacts.get(name.strip().lower())


class AndroidTool(BaseTool):
    """Android phone integration via ADB. Requires USB debugging enabled."""

    @property
    def name(self) -> str:
        return "android"

    @property
    def description(self) -> str:
        return (
            "Controls an Android phone connected via USB with ADB. "
            "Use this tool ONLY for phone/SMS/WhatsApp actions. "
            "Actions: "
            "action=call – make a phone call. Examples: 'Call Amma', 'Call Dad', 'Dadకి కాల్ చేయి', 'Ammaకి కాల్ చేయి'. "
            "action=sms – send an SMS. Examples: 'Message Ravi Hello', 'Raviకి Hello అని మెసేజ్ పంపు', 'రవికి మెసేజ్ పంపు'. "
            "action=whatsapp – send a WhatsApp message. Examples: 'WhatsApp Amma Hi', 'అమ్మకి WhatsApp పంపు', 'Saiకి వాట్సాప్ పంపు'. "
            "action=read_notifications – read phone notifications. "
            "action=read_contacts – list saved contacts. "
            "The 'contact' parameter is the person's name (e.g. 'Amma', 'Dad', 'Ravi'). "
            "The 'message' parameter is the text to send (required for sms and whatsapp). "
            "NEVER use this tool to open apps, browse the web, or search."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["call", "sms", "whatsapp", "read_notifications", "read_contacts"],
                    "description": "The Android action to perform.",
                },
                "contact": {
                    "type": "string",
                    "description": "Contact name or phone number (required for call, sms, whatsapp).",
                },
                "message": {
                    "type": "string",
                    "description": "Message text (required for sms and whatsapp actions).",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "").strip().lower()
        contact_name = kwargs.get("contact", "").strip()
        message = kwargs.get("message", "").strip()

        if action == "read_contacts":
            return self._read_contacts()
        elif action == "read_notifications":
            return self._read_notifications()
        elif action in ("call", "sms", "whatsapp"):
            if not contact_name:
                return "Failure: 'contact' is required for this action."
            # Resolve name to phone number
            phone = _resolve_contact(contact_name)
            if not phone:
                # Try treating the contact itself as a phone number
                if contact_name.lstrip("+").isdigit():
                    phone = contact_name
                else:
                    return f"Failure: Contact '{contact_name}' not found. Add them to data/contacts.json."
            if action == "call":
                return self._make_call(phone, contact_name)
            elif action == "sms":
                if not message:
                    return "Failure: 'message' is required for SMS."
                return self._send_sms(phone, contact_name, message)
            elif action == "whatsapp":
                if not message:
                    return "Failure: 'message' is required for WhatsApp."
                return self._send_whatsapp(phone, contact_name, message)
        return f"Failure: Unknown action '{action}'."

    def _make_call(self, phone: str, name: str) -> str:
        logger.info("[Android] Initiating call to %s (%s)", name, phone)
        ok, out = _run_adb(["shell", "am", "start", "-a", "android.intent.action.CALL",
                            "-d", f"tel:{phone}"])
        if ok:
            return f"Success: Calling {name} ({phone})."
        return f"Failure: Could not initiate call. {out}"

    def _send_sms(self, phone: str, name: str, message: str) -> str:
        logger.info("[Android] Sending SMS to %s (%s): %s", name, phone, message)
        # Open the SMS app with pre-filled recipient and message
        ok, out = _run_adb([
            "shell", "am", "start", "-a", "android.intent.action.SENDTO",
            "-d", f"sms:{phone}",
            "--es", "sms_body", message,
            "--ez", "exit_on_sent", "true"
        ])
        if ok:
            return f"Success: SMS composed for {name}. Please send from phone."
        return f"Failure: Could not open SMS. {out}"

    def _send_whatsapp(self, phone: str, name: str, message: str) -> str:
        logger.info("[Android] Opening WhatsApp for %s (%s): %s", name, phone, message)
        # Strip non-digits for WhatsApp (international format without +)
        wa_phone = "".join(ch for ch in phone if ch.isdigit())
        ok, out = _run_adb([
            "shell", "am", "start", "-a", "android.intent.action.VIEW",
            "-d", f"https://api.whatsapp.com/send?phone={wa_phone}&text={message}"
        ])
        if ok:
            return f"Success: WhatsApp opened for {name}. Please send from phone."
        return f"Failure: Could not open WhatsApp. {out}"

    def _read_notifications(self) -> str:
        logger.info("[Android] Reading active notifications via ADB")
        ok, out = _run_adb(["shell", "dumpsys", "notification", "--noredact"], timeout=15)
        if not ok:
            return f"Failure: Could not read notifications. {out}"
        # Parse just the notification titles/texts
        lines = [l.strip() for l in out.splitlines() if "android.title" in l or "android.text" in l]
        if not lines:
            return "No active notifications found."
        summary = "\n".join(lines[:20])  # limit output
        return f"Active notifications:\n{summary}"

    def _read_contacts(self) -> str:
        contacts = _load_contacts()
        if not contacts:
            return "No contacts found in data/contacts.json."
        lines = [f"{name.title()}: {phone}" for name, phone in contacts.items()]
        return "Saved contacts:\n" + "\n".join(lines)
