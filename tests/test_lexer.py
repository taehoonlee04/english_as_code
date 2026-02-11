"""Tests for EAC lexer."""

import pytest
from eac.lexer import tokenize, TokenKind


def test_tokenize_simple():
    tokens = tokenize('Set x to 1.')
    kinds = [t.kind for t in tokens]
    assert TokenKind.KEYWORD in kinds
    assert TokenKind.IDENT in kinds
    assert TokenKind.NUMBER in kinds
    assert TokenKind.DOT in kinds
    assert TokenKind.EOF in kinds


def test_tokenize_keywords():
    tokens = tokenize("Open workbook \"foo.xlsx\".")
    assert tokens[0].kind == TokenKind.KEYWORD and tokens[0].value == "Open"
    assert tokens[1].kind == TokenKind.KEYWORD and tokens[1].value == "workbook"
    assert tokens[2].kind == TokenKind.STRING and tokens[2].value == "foo.xlsx"


def test_tokenize_comparison_ops():
    tokens = tokenize("Filter T where x > 0.")
    assert any(t.kind == TokenKind.GT and t.value == ">" for t in tokens)
