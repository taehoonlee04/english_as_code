"""AST node definitions for EAC. Every sentence template maps to one or more node types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AggOp(Enum):
    SUM = "sum"
    COUNT = "count"
    MIN = "min"
    MAX = "max"


class CompOp(Enum):
    EQ = "="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    CONTAINS = "contains"
    IN = "in"


@dataclass
class SourceLoc:
    line: int
    column: int
    path: Optional[str] = None


# --- Expressions ---

class Expr:
    """Base for all expressions; no fields so subclasses control field order."""
    pass


@dataclass
class NumberLit(Expr):
    value: float
    loc: Optional[SourceLoc] = None


@dataclass
class StringLit(Expr):
    value: str
    loc: Optional[SourceLoc] = None


@dataclass
class MoneyLit(Expr):
    currency: str
    amount: float
    loc: Optional[SourceLoc] = None


@dataclass
class DateLit(Expr):
    value: str  # YYYY-MM-DD
    loc: Optional[SourceLoc] = None


@dataclass
class Identifier(Expr):
    name: str
    loc: Optional[SourceLoc] = None


@dataclass
class QualifiedRef(Expr):
    """table.column or row.column"""
    base: str  # table name or "row"
    field: str
    loc: Optional[SourceLoc] = None


@dataclass
class BinaryExpr(Expr):
    left: Expr
    op: str  # "+", "-", "*", "/", "and", "or", CompOp
    right: Expr
    loc: Optional[SourceLoc] = None


@dataclass
class Comparison(Expr):
    left: Expr
    op: CompOp
    right: Expr
    loc: Optional[SourceLoc] = None


@dataclass
class FunctionCall(Expr):
    name: str
    args: list[Expr] = field(default_factory=list)
    loc: Optional[SourceLoc] = None


# --- Statements ---

class Statement:
    """Base for statements; subclasses are dataclasses with loc last."""

@dataclass
class OpenWorkbook(Statement):
    path: str
    loc: Optional[SourceLoc] = None


@dataclass
class TreatRangeAsTable(Statement):
    sheet: str
    range_spec: str  # e.g. "A1:G999"
    table_name: str
    loc: Optional[SourceLoc] = None


@dataclass
class SetVar(Statement):
    name: str
    value: Expr
    loc: Optional[SourceLoc] = None


@dataclass
class AddColumn(Statement):
    table: str
    name: str
    expr: Expr
    loc: Optional[SourceLoc] = None


@dataclass
class FilterTable(Statement):
    table: str
    condition: Expr
    loc: Optional[SourceLoc] = None


@dataclass
class SortTable(Statement):
    table: str
    by: Expr
    ascending: bool
    loc: Optional[SourceLoc] = None


@dataclass
class GroupTable(Statement):
    table: str
    by: Expr
    aggregates: list[tuple[AggOp, Expr, str]]  # (op, column_expr, result_name)
    loc: Optional[SourceLoc] = None


@dataclass
class ExportTable(Statement):
    source: Expr
    path: str
    loc: Optional[SourceLoc] = None


@dataclass
class CallResult(Statement):
    name: str
    loc: Optional[SourceLoc] = None


# Web
@dataclass
class UseSystem(Statement):
    name: str
    version: str
    loc: Optional[SourceLoc] = None


@dataclass
class LogIn(Statement):
    credential: str
    loc: Optional[SourceLoc] = None


@dataclass
class LogOut(Statement):
    loc: Optional[SourceLoc] = None


@dataclass
class GoToPage(Statement):
    page: str
    loc: Optional[SourceLoc] = None


@dataclass
class EnterField(Statement):
    field_id: str
    value: Expr
    loc: Optional[SourceLoc] = None


@dataclass
class ClickElement(Statement):
    element_id: str
    loc: Optional[SourceLoc] = None


@dataclass
class VerifyCondition(Statement):
    condition: Expr
    loc: Optional[SourceLoc] = None


@dataclass
class ExtractField(Statement):
    var_name: str
    selector: str
    loc: Optional[SourceLoc] = None


# Control
@dataclass
class ForEach(Statement):
    var: str
    collection: Expr
    body: list[Statement]
    loc: Optional[SourceLoc] = None


@dataclass
class IfElse(Statement):
    condition: Expr
    then_body: list[Statement]
    else_body: list[Statement]
    loc: Optional[SourceLoc] = None


@dataclass
class OnError(Statement):
    action: str  # "retry", "skip", "stop", "Continue", "escalate"
    value: Optional[str] = None  # for retry N or escalate "msg"
    loc: Optional[SourceLoc] = None


@dataclass
class Comment(Statement):
    text: str
    loc: Optional[SourceLoc] = None


# --- Program ---

@dataclass
class Program:
    statements: list[Statement]
    path: Optional[str] = None
