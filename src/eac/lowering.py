"""Lower typed AST to deterministic IR (JSON-serializable)."""

from eac.ast_nodes import Program, Statement
from eac.ir import IRProgram, IRStep


def lower(program: Program) -> IRProgram:
    """Produce IR from AST. Runtime executes IR only."""
    ir = IRProgram()
    idx = [0]

    def add_steps(statements: list[Statement]) -> None:
        for stmt in statements:
            idx[0] += 1
            step = _stmt_to_step(stmt, idx[0], idx)
            if step:
                ir.steps.append(step)

    add_steps(program.statements)
    return ir


def _stmt_to_step(stmt: Statement, index: int, counter: list[int] | None = None) -> IRStep | None:
    """Map one statement to an IR step. Returns None for no-ops (e.g. comments)."""
    from eac.ast_nodes import (
        OpenWorkbook,
        TreatRangeAsTable,
        SetVar,
        AddColumn,
        FilterTable,
        ExportTable,
        CallResult,
        UseSystem,
        LogIn,
        LogOut,
        GoToPage,
        EnterField,
        ClickElement,
        ExtractField,
    )
    step_id = f"step_{index:03d}"
    if isinstance(stmt, OpenWorkbook):
        return IRStep(id=step_id, op="excel.open_workbook", args={"path": stmt.path})
    if isinstance(stmt, TreatRangeAsTable):
        return IRStep(
            id=step_id,
            op="excel.read_table",
            args={"sheet": stmt.sheet, "range": stmt.range_spec},
            result=stmt.table_name,
            result_type="table",
        )
    if isinstance(stmt, SetVar):
        return IRStep(
            id=step_id,
            op="set_var",
            args={"name": stmt.name, "value": _expr_to_arg(stmt.value)},
            result=stmt.name,
        )
    if isinstance(stmt, AddColumn):
        return IRStep(
            id=step_id,
            op="table.add_column",
            args={
                "table": stmt.table,
                "name": stmt.name,
                "expr": _expr_to_arg(stmt.expr),
            },
            result=stmt.table,
            result_type="table",
        )
    if isinstance(stmt, FilterTable):
        return IRStep(
            id=step_id,
            op="table.filter",
            args={"table": stmt.table, "condition": _expr_to_arg(stmt.condition)},
            result=stmt.table,
            result_type="table",
        )
    if isinstance(stmt, ExportTable):
        return IRStep(
            id=step_id,
            op="excel.export",
            args={"source": _expr_to_arg(stmt.source), "path": stmt.path},
        )
    if isinstance(stmt, CallResult):
        return IRStep(id=step_id, op="call_result", args={"name": stmt.name}, result=stmt.name)
    if isinstance(stmt, UseSystem):
        return IRStep(
            id=step_id,
            op="web.use_system",
            args={"name": stmt.name, "version": stmt.version},
        )
    if isinstance(stmt, LogIn):
        return IRStep(id=step_id, op="web.login", args={"credential": stmt.credential})
    if isinstance(stmt, LogOut):
        return IRStep(id=step_id, op="web.logout", args={})
    if isinstance(stmt, GoToPage):
        return IRStep(id=step_id, op="web.goto_page", args={"page": stmt.page})
    if isinstance(stmt, EnterField):
        return IRStep(
            id=step_id,
            op="web.enter",
            args={"field": stmt.field_id, "value": _expr_to_arg(stmt.value)},
        )
    if isinstance(stmt, ClickElement):
        return IRStep(id=step_id, op="web.click", args={"element": stmt.element_id})
    if isinstance(stmt, ExtractField):
        return IRStep(
            id=step_id,
            op="web.extract",
            args={"selector": stmt.selector},
            result=stmt.var_name,
        )
    from eac.ast_nodes import ForEach
    if isinstance(stmt, ForEach):
        ctr = counter or [0]
        body_steps = []
        for s in stmt.body:
            ctr[0] += 1
            sub = _stmt_to_step(s, ctr[0], ctr)
            if sub:
                body_steps.append({"id": sub.id, "op": sub.op, "args": sub.args, "result": sub.result, "type": sub.result_type})
        return IRStep(
            id=step_id,
            op="control.for_each",
            args={
                "var": stmt.var,
                "collection": _expr_to_arg(stmt.collection),
                "body": body_steps,
            },
        )
    return None


def _expr_to_arg(expr: Any) -> Any:
    """Turn an AST expression into a JSON-serializable value for IR args."""
    from eac.ast_nodes import (
        NumberLit,
        StringLit,
        MoneyLit,
        DateLit,
        Identifier,
        QualifiedRef,
    )
    if isinstance(expr, NumberLit):
        return {"type": "number", "value": expr.value}
    if isinstance(expr, StringLit):
        return {"type": "string", "value": expr.value}
    if isinstance(expr, MoneyLit):
        return {"type": "money", "currency": expr.currency, "amount": expr.amount}
    if isinstance(expr, DateLit):
        return {"type": "date", "value": expr.value}
    if isinstance(expr, Identifier):
        return {"type": "ref", "name": expr.name}
    if isinstance(expr, QualifiedRef):
        return {"type": "qualified", "base": expr.base, "field": expr.field}
    return {"type": "unknown"}
