from core.brain.intent import IntentType
from core.brain.action_plan import ActionPlan

class BrainRouter:
    """Routes ActionPlan based on confidence thresholds and categories."""

    def __init__(self, confidence_threshold: float = 0.5) -> None:
        self.confidence_threshold = confidence_threshold

    def route(self, plan: ActionPlan) -> ActionPlan:
        # Check confidence
        if plan.confidence < self.confidence_threshold:
            # Return clarification prompt plan instead of guessing
            if plan.intent == IntentType.OPEN:
                return ActionPlan(
                    IntentType.CLARIFICATION, "PROMPT", 
                    "Which application or website should I open?", 
                    parameters={"original_plan": plan}, confidence=1.0
                )
            if plan.intent == IntentType.CLOSE:
                return ActionPlan(
                    IntentType.CLARIFICATION, "PROMPT", 
                    "Which application should I close?", 
                    parameters={"original_plan": plan}, confidence=1.0
                )
            return ActionPlan(
                IntentType.CLARIFICATION, "PROMPT", 
                "I'm sorry, I'm not sure how to execute that command. Could you please clarify?", 
                parameters={"original_plan": plan}, confidence=1.0
            )
        return plan
