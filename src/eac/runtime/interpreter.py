"""Deterministic interpreter: execute IR steps via tool registry."""

import json
from pathlib import Path
from typing import Any, Optional

from eac.ir import IRProgram, IRStep
from eac.runtime.tools import TOOLS


def _resolve_refs(value: Any, env: dict[str, Any]) -> Any:
    """Recursively replace refs and qualified refs (e.g. row.field) from env."""
    if isinstance(value, dict):
        if value.get("type") == "ref" and value.get("name") in env:
            return env[value["name"]]
        if value.get("type") == "qualified":
            base = value.get("base")
            field = value.get("field")
            if base is not None and field is not None and base in env:
                row_or_table = env[base]
                if isinstance(row_or_table, dict):
                    return row_or_table.get(field)
            return value
        return {k: _resolve_refs(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(v, env) for v in value]
    return value


def _run_one_step(
    step: IRStep | dict,
    env: dict[str, Any],
    trace: list[dict],
    dry_run: bool,
) -> Any:
    """Run a single step (IRStep or body step dict). Update env, append to trace. Return result."""
    if isinstance(step, dict):
        step_id = step.get("id", "")
        op = step.get("op", "")
        step_args = dict(step.get("args", {}))
        result_name = step.get("result")
    else:
        step_id = step.id
        op = step.op
        step_args = dict(step.args)
        result_name = step.result

    args = _resolve_refs(step_args, env)
    if op.startswith("table.") and isinstance(args.get("table"), str) and args["table"] in env:
        args["table"] = env[args["table"]]
    if op == "excel.export" and isinstance(args.get("source"), str) and args["source"] in env:
        args["source"] = env[args["source"]]

    if dry_run:
        trace.append({"id": step_id, "op": op, "args": args, "dry_run": True})
        return None

    fn = TOOLS.get(op)
    if fn is None:
        raise RuntimeError(f"Unknown operation: {op}")
    result = fn(**args)
    if result_name:
        env[result_name] = result
    trace.append({"id": step_id, "op": op, "args": args, "result": result})
    return result


def run(ir: IRProgram, dry_run: bool = False, trace_path: Optional[Path] = None) -> list[dict]:
    """Execute IR steps. Log each step to trace. Return list of step results."""
    trace: list[dict] = []
    env: dict[str, Any] = {}

    for step in ir.steps:
        op = step.op
        args = _resolve_refs(dict(step.args), env)

        if op == "control.for_each":
            collection = args.get("collection")
            var = args.get("var", "row")
            body = args.get("body") or []
            if dry_run:
                trace.append({"id": step.id, "op": op, "args": {**args, "body": body}, "dry_run": True})
                continue
            if not isinstance(collection, list):
                raise RuntimeError("For each collection must be a table (list of rows).")
            for row in collection:
                env[var] = row if isinstance(row, dict) else {}
                for body_step in body:
                    _run_one_step(body_step, env, trace, dry_run=False)
            env.pop(var, None)
            continue

        # Resolve table/source by name for ops that take a table
        if op.startswith("table.") and isinstance(args.get("table"), str) and args["table"] in env:
            args["table"] = env[args["table"]]
        if op == "excel.export" and isinstance(args.get("source"), str) and args["source"] in env:
            args["source"] = env[args["source"]]

        if dry_run:
            trace.append({"id": step.id, "op": op, "args": args, "dry_run": True})
            continue

        fn = TOOLS.get(op)
        if fn is None:
            raise RuntimeError(f"Unknown operation: {op}")
        result = fn(**args)
        if step.result:
            env[step.result] = result
        trace.append({"id": step.id, "op": op, "args": args, "result": result})

    if trace_path:
        with open(trace_path, "w") as f:
            for entry in trace:
                f.write(json.dumps(entry, default=str) + "\n")
    return trace
