"""IR (Intermediate Representation) definitions. AST lowers to JSON-serializable IR."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class IRStep:
    id: str
    op: str
    args: dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    result_type: Optional[str] = None


@dataclass
class IRProgram:
    version: str = "0.1.0"
    steps: list[IRStep] = field(default_factory=list)
    error_policy: dict[str, str] = field(default_factory=lambda: {"default": "stop"})
    permissions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "steps": [
                {
                    "id": s.id,
                    "op": s.op,
                    "args": s.args,
                    "result": s.result,
                    "type": s.result_type,
                }
                for s in self.steps
            ],
            "error_policy": self.error_policy,
            "permissions": self.permissions,
        }
