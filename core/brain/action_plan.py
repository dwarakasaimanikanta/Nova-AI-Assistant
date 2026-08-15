from dataclasses import dataclass, field
from typing import Any, Dict
from core.brain.intent import IntentType

@dataclass
class ActionPlan:
    intent: IntentType
    target_type: str  # WEBSITE, APPLICATION, FOLDER, FILE, KNOWLEDGE, PROJECT, etc.
    target: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
