"""Deterministic interpreter: execute IR steps via tool registry."""

import json
from pathlib import Path
from typing import Any, Optional

from eac.ir import IRProgram, IRStep
from eac.runtime.tools import TOOLS


def run(ir: IRProgram, dry_run: bool = False, trace_path: Optional[Path] = None) -> list[dict]:
    """Execute IR steps. Log each step to trace. Return list of step results."""
    trace: list[dict] = []
    env: dict[str, Any] = {}

    for step in ir.steps:
        op = step.op
        args = dict(step.args)

        # Resolve refs from env
        for k, v in args.items():
            if isinstance(v, dict) and v.get("type") == "ref" and v.get("name") in env:
                args[k] = env[v["name"]]

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
