"""CLI tests using typer.testing.CliRunner (Context7 style)."""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from eac.cli import app

runner = CliRunner()


def test_parse_success(example_file):
    result = runner.invoke(app, ["parse", str(example_file)])
    assert result.exit_code == 0
    assert "Parsed" in result.output


def test_parse_missing_file():
    result = runner.invoke(app, ["parse", "nonexistent.eac"])
    assert result.exit_code == 1
    assert "not found" in result.stderr.lower() or "Error" in result.stderr


def test_check_success(example_file):
    result = runner.invoke(app, ["check", str(example_file)])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_lower_success(example_file):
    result = runner.invoke(app, ["lower", str(example_file)])
    assert result.exit_code == 0
    assert "steps" in result.output or "version" in result.output


def test_run_dry_run(example_file):
    result = runner.invoke(app, ["run", str(example_file), "--dry-run"])
    assert result.exit_code == 0
    assert "Completed" in result.output and "dry run" in result.output


def test_explain_success(example_file):
    result = runner.invoke(app, ["explain", str(example_file)])
    assert result.exit_code == 0
    assert "Steps:" in result.output


def test_run_fails_on_type_error(tmp_path):
    """Run exits with 1 and prints type-check error when program has undeclared name."""
    bad = tmp_path / "bad.eac"
    bad.write_text('Filter NoSuchTable where NoSuchTable.x > 0.')
    result = runner.invoke(app, ["run", str(bad)])
    assert result.exit_code == 1
    assert "not defined" in result.stdout.lower() or "not defined" in result.stderr.lower()


def test_trace_missing_trace_file():
    """trace command exits 1 when no .trace.jsonl exists for the given file."""
    result = runner.invoke(app, ["trace", "tests/examples/nonexistent_never_run.eac"])
    assert result.exit_code == 1
    assert "No trace" in result.stderr or "not found" in result.stderr.lower()
