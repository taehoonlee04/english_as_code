"""Tests for EAC type checker."""

import pytest
from eac.parser import parse
from eac.type_checker import check
from eac.errors import TypeCheckError


def test_check_valid_program():
    source = '''
Open workbook "x.xlsx".
In sheet "S", treat range A1B2 as table T.
Set today to date "2026-02-11".
Filter T where T.Balance > USD 0.00.
Export T to "out.csv".
'''
    program = parse(source)
    check(program)


def test_check_undeclared_table_raises():
    source = 'Filter MissingTable where MissingTable.x > 0.'
    program = parse(source)
    with pytest.raises(TypeCheckError) as exc_info:
        check(program)
    assert "not defined" in str(exc_info.value).lower() or "MissingTable" in str(exc_info.value)


def test_check_undeclared_var_in_expr_raises():
    source = '''
Open workbook "x.xlsx".
In sheet "S", treat range A1B2 as table T.
Set x to missing_var.
'''
    program = parse(source)
    with pytest.raises(TypeCheckError) as exc_info:
        check(program)
    assert "not defined" in str(exc_info.value).lower()


def test_check_for_each_row_scope():
    source = '''
Open workbook "x.xlsx".
In sheet "S", treat range A1B2 as table Invoices.
For each row in Invoices:
    Set x to row.Amount.
'''
    program = parse(source)
    check(program)
