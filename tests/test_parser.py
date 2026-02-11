"""Tests for EAC parser."""

import pytest
from pathlib import Path

from eac.parser import parse
from eac.ast_nodes import OpenWorkbook, SetVar, FilterTable, ForEach, ExportTable


def test_parse_open_workbook():
    source = 'Open workbook "data/ar.xlsx".'
    program = parse(source)
    assert len(program.statements) == 1
    assert isinstance(program.statements[0], OpenWorkbook)
    assert program.statements[0].path == "data/ar.xlsx"


def test_parse_set_and_filter():
    source = """
Set today to date "2026-02-11".
Filter OpenItems where OpenItems.Balance > USD 0.00.
"""
    program = parse(source)
    assert len(program.statements) == 2
    assert isinstance(program.statements[0], SetVar)
    assert isinstance(program.statements[1], FilterTable)
    assert program.statements[1].table == "OpenItems"


def test_all_examples_parse(example_file):
    """Parametrized: every example .eac file parses to at least one statement."""
    program = parse(example_file.read_text(), path=str(example_file))
    assert len(program.statements) >= 1


def test_parse_example_aging_report(examples_dir):
    path = examples_dir / "aging_report.eac"
    program = parse(path.read_text(), path=str(path))
    assert len(program.statements) >= 4


def test_parse_example_erp(examples_dir):
    path = examples_dir / "erp_invoice_post.eac"
    program = parse(path.read_text(), path=str(path))
    assert any(isinstance(s, ForEach) for s in program.statements)


@pytest.mark.parametrize("source,expected_count", [
    ('Open workbook "x.xlsx".', 1),
    ('Set x to 1.', 1),
    ('Open workbook "a.xlsx".\nSet y to 2.', 2),
])
def test_parse_statement_count(source, expected_count):
    program = parse(source)
    assert len(program.statements) == expected_count
