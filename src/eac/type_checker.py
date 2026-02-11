"""Type checker: walk AST, build symbol table, reject type errors."""

from typing import Any, Optional

from eac.ast_nodes import Program, Statement
from eac.errors import TypeCheckError


def check(program: Program) -> None:
    """Type-check the program. Raises TypeCheckError on failure."""
    # TODO: build symbol table from declarations, check each statement
    pass
