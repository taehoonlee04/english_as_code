"""Tests for AST -> IR lowering."""

import pytest
from eac.parser import parse
from eac.lowering import lower


def test_lower_open_workbook():
    program = parse('Open workbook "data/ar.xlsx".')
    ir = lower(program)
    assert len(ir.steps) == 1
    assert ir.steps[0].op == "excel.open_workbook"
    assert ir.steps[0].args["path"] == "data/ar.xlsx"


def test_lower_export():
    program = parse('Set x to 1.\nExport x to "out.csv".')
    ir = lower(program)
    assert any(s.op == "excel.export" for s in ir.steps)
