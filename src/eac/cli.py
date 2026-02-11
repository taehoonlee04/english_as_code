"""CLI entry point: parse, check, lower, run, explain, trace."""

import json
import sys
from pathlib import Path

import typer

from eac import __version__
from eac.errors import EACError, ParseError
from eac.ir import IRProgram
from eac.lowering import lower
from eac.parser import parse
from eac.runtime.interpreter import run
from eac.type_checker import check

app = typer.Typer(
    name="eac",
    help="English as Code — run EAC programs (parse, check, lower, run).",
)


def _load_source(path: Path) -> str:
    if not path.exists():
        typer.echo(f"Error: file not found: {path}", err=True)
        raise typer.Exit(1)
    return path.read_text()


def _parse_and_catch(path: Path):
    source = _load_source(path)
    try:
        return parse(source, path=str(path))
    except ParseError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


@app.command("parse")
def parse_cmd(file: Path = typer.Argument(..., help=".eac file")):
    """Parse file and print AST (debug)."""
    program = _parse_and_catch(file)
    typer.echo(f"Parsed {len(program.statements)} statements.")
    for i, s in enumerate(program.statements):
        typer.echo(f"  {i + 1}. {type(s).__name__}")


@app.command("check")
def check_cmd(file: Path = typer.Argument(..., help=".eac file")):
    """Type-check the program."""
    program = _parse_and_catch(file)
    try:
        check(program)
        typer.echo("OK")
    except EACError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


@app.command("lower")
def lower_cmd(file: Path = typer.Argument(..., help=".eac file")):
    """Emit IR JSON to stdout."""
    program = _parse_and_catch(file)
    ir = lower(program)
    typer.echo(json.dumps(ir.to_dict(), indent=2))


@app.command("run")
def run_cmd(
    file: Path = typer.Argument(..., help=".eac file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate only, do not execute"),
):
    """Parse, type-check, lower, and execute the program."""
    program = _parse_and_catch(file)
    try:
        check(program)
    except EACError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    ir = lower(program)
    trace_path = file.with_suffix(file.suffix + ".trace.jsonl")
    try:
        trace = run(ir, dry_run=dry_run, trace_path=trace_path)
        typer.echo(f"Completed {len(trace)} steps." + (" (dry run)" if dry_run else ""))
        if trace_path.exists():
            typer.echo(f"Trace: {trace_path}")
    except Exception as e:
        typer.echo(f"Runtime error: {e}", err=True)
        raise typer.Exit(1)


@app.command("explain")
def explain_cmd(file: Path = typer.Argument(..., help=".eac file")):
    """Print plain-English summary of what the program does (from IR)."""
    program = _parse_and_catch(file)
    ir = lower(program)
    typer.echo("Steps:")
    for s in ir.steps:
        typer.echo(f"  - {s.op}: {s.args}")


@app.command("trace")
def trace_cmd(file: Path = typer.Argument(..., help=".eac file")):
    """Show last execution trace for this program."""
    trace_path = file.with_suffix(file.suffix + ".trace.jsonl")
    if not trace_path.exists():
        typer.echo(f"No trace found: {trace_path}", err=True)
        raise typer.Exit(1)
    for line in trace_path.read_text().strip().split("\n"):
        if line:
            typer.echo(line)


@app.callback()
def main():
    """English as Code (EAC) — deterministic CNL for Excel and web automation."""
    pass


if __name__ == "__main__":
    app()
