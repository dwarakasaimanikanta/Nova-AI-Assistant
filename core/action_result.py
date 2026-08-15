from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class ActionResult:
    """
    Structured action result returned by all tools.
    Provides verified properties to prevent the response generator
    from inventing tool success.
    """
    success: bool
    action: str
    target: str
    details: str = ""
    error: Optional[str] = None
    verification: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        # Compatibility helper so casting to string produces a clean prefix
        prefix = "Success" if self.success else "Failure"
        err_suffix = f": {self.error}" if self.error else ""
        details_suffix = f": {self.details}" if self.details else ""
        
        if not self.success:
            return f"{prefix}{err_suffix}{details_suffix}"
        return f"{prefix}{details_suffix}"

    def __contains__(self, item: str) -> bool:
        return item in str(self)

    def startswith(self, prefix: str, *args, **kwargs) -> bool:
        return str(self).startswith(prefix, *args, **kwargs)

    def endswith(self, suffix: str, *args, **kwargs) -> bool:
        return str(self).endswith(suffix, *args, **kwargs)

    def lower(self) -> str:
        return str(self).lower()

    def upper(self) -> str:
        return str(self).upper()

    def split(self, *args, **kwargs):
        return str(self).split(*args, **kwargs)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return str(self) == other or self.details == other
        if not isinstance(other, ActionResult):
            return False
        return (self.success == other.success and
                self.action == other.action and
                self.target == other.target and
                self.details == other.details and
                self.error == other.error and
                self.verification == other.verification)


