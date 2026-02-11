"""Structured errors for EAC (parse, type, runtime)."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class EACError(Exception):
    """Base for all EAC errors."""
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    path: Optional[str] = None

    def __str__(self) -> str:
        loc = ""
        if self.path:
            loc = f"{self.path}:"
        if self.line is not None:
            loc += f"{self.line}"
            if self.column is not None:
                loc += f":{self.column}"
            loc += ": "
        return f"{loc}{self.message}"


class ParseError(EACError):
    """Source did not match grammar or tokenization failed."""
    pass


class TypeCheckError(EACError):
    """Type checker found an error (undeclared name, type mismatch, etc.)."""
    pass


class RuntimeError(EACError):
    """Runtime execution failed (tool error, timeout, etc.)."""
    pass
