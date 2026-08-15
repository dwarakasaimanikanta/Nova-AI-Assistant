from core.brain.command_parser import CommandParser
from core.brain.router import BrainRouter
from core.brain.action_plan import ActionPlan

class NovaBrain:
    """NOVA Brain Orchestration layer coordinating parsing and routing."""

    def __init__(self, confidence_threshold: float = 0.5) -> None:
        self.parser = CommandParser()
        self.router = BrainRouter(confidence_threshold=confidence_threshold)

    def process(self, text: str) -> ActionPlan:
        plan = self.parser.parse(text)
        return self.router.route(plan)
