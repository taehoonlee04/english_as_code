"""Type checker: walk AST, build symbol table, reject type errors."""

from typing import Any, Optional

from eac.ast_nodes import (
    AddColumn,
    BinaryExpr,
    Comparison,
    Expr,
    ExportTable,
    FilterTable,
    ForEach,
    Identifier,
    NotExpr,
    Program,
    QualifiedRef,
    SetVar,
    SortTable,
    Statement,
    TreatRangeAsTable,
)
from eac.errors import TypeCheckError


def check(program: Program) -> None:
    """Type-check the program. Raises TypeCheckError on failure."""
    symbols: dict[str, str] = {}  # name -> type ("table", "row", "number", "string", "date", "money", "any")

    def ensure_declared(name: str, loc: Optional[Any]) -> None:
        if name not in symbols:
            line = loc.line if loc else None
            col = loc.column if loc else None
            path = loc.path if loc and hasattr(loc, "path") else program.path
            raise TypeCheckError(
                f"{name!r} is not defined. Use a table or variable that was declared earlier.",
                line=line,
                column=col,
                path=path,
            )

    def check_expr(
        expr: Expr, symbols_here: dict[str, str], allow_undeclared: bool = False
    ) -> None:
        if isinstance(expr, Identifier):
            if not allow_undeclared:
                ensure_declared(expr.name, expr.loc)
        elif isinstance(expr, QualifiedRef):
            if expr.base != "row":
                ensure_declared(expr.base, expr.loc)
        elif isinstance(expr, Comparison):
            check_expr(expr.left, symbols_here, allow_undeclared)
            check_expr(expr.right, symbols_here, allow_undeclared)
        elif isinstance(expr, BinaryExpr):
            check_expr(expr.left, symbols_here, allow_undeclared)
            check_expr(expr.right, symbols_here, allow_undeclared)
        elif isinstance(expr, NotExpr):
            check_expr(expr.expr, symbols_here, allow_undeclared)

    def check_statement(stmt: Statement, symbols_here: dict[str, str]) -> None:
        if isinstance(stmt, TreatRangeAsTable):
            symbols_here[stmt.table_name] = "table"
            return
        if isinstance(stmt, SetVar):
            check_expr(stmt.value, symbols_here)
            symbols_here[stmt.name] = "any"
            return
        if isinstance(stmt, AddColumn):
            ensure_declared(stmt.table, stmt.loc)
            check_expr(stmt.expr, symbols_here)
            return
        if isinstance(stmt, FilterTable):
            ensure_declared(stmt.table, stmt.loc)
            check_expr(stmt.condition, symbols_here, allow_undeclared=True)
            return
        if isinstance(stmt, SortTable):
            ensure_declared(stmt.table, stmt.loc)
            check_expr(stmt.by, symbols_here)
            return
        if isinstance(stmt, ExportTable):
            check_expr(stmt.source, symbols_here)
            return
        if isinstance(stmt, ForEach):
            check_expr(stmt.collection, symbols_here)
            body_symbols = dict(symbols_here)
            body_symbols[stmt.var] = "row"
            for s in stmt.body:
                check_statement(s, body_symbols)
            return
        # Other statement types: no new symbols or refs to check
        if hasattr(stmt, "value") and isinstance(getattr(stmt, "value"), Expr):
            check_expr(getattr(stmt, "value"), symbols_here)
        if hasattr(stmt, "condition") and isinstance(getattr(stmt, "condition"), Expr):
            check_expr(getattr(stmt, "condition"), symbols_here)

    for stmt in program.statements:
        check_statement(stmt, symbols)
