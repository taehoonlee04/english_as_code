"""Recursive-descent parser: tokens -> AST. One production per grammar rule."""

from typing import Any, Optional

from eac.ast_nodes import (
    AddColumn,
    BinaryExpr,
    CallResult,
    ClickElement,
    Comparison,
    CompOp,
    DateLit,
    ExportTable,
    FilterTable,
    ForEach,
    GoToPage,
    Identifier,
    LogIn,
    LogOut,
    MoneyLit,
    NumberLit,
    OpenWorkbook,
    Program,
    QualifiedRef,
    SetVar,
    SourceLoc,
    Statement,
    StringLit,
    TreatRangeAsTable,
    UseSystem,
    EnterField,
    ExtractField,
)
from eac.errors import ParseError
from eac.lexer import Token, TokenKind, tokenize


class Parser:
    def __init__(self, tokens: list[Token], path: Optional[str] = None):
        self.tokens = tokens
        self.path = path
        self.pos = 0

    def peek(self) -> Token:
        if self.pos >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[self.pos]

    def advance(self) -> Token:
        t = self.peek()
        if self.pos < len(self.tokens):
            self.pos += 1
        return t

    def at(self, kind: str, value: Any = None) -> bool:
        t = self.peek()
        if t.kind != kind:
            return False
        if value is not None and t.value != value:
            return False
        return True

    def expect(self, kind: str, value: Any = None) -> Token:
        t = self.advance()
        if t.kind != kind:
            raise ParseError(
                f"Expected {kind}" + (f" {value!r}" if value else "") + f", got {t.kind} {t.value!r}",
                t.line, t.column, self.path,
            )
        if value is not None and t.value != value:
            raise ParseError(f"Expected {value!r}, got {t.value!r}", t.line, t.column, self.path)
        return t

    def loc(self, token: Token) -> SourceLoc:
        return SourceLoc(token.line, token.column, self.path)

    def parse_program(self) -> Program:
        statements: list[Statement] = []
        while not self.at(TokenKind.EOF):
            while self.at(TokenKind.NEWLINE):
                self.advance()
            if self.at(TokenKind.EOF):
                break
            stmt = self.parse_statement()
            if stmt is not None:
                statements.append(stmt)
        return Program(statements=statements, path=self.path)

    def parse_statement(self) -> Optional[Statement]:
        if self.at(TokenKind.EOF):
            return None
        t = self.peek()

        # For each row in X:
        if self.at(TokenKind.KEYWORD, "For"):
            return self.parse_for_each()

        # Open workbook "..."
        if self.at(TokenKind.KEYWORD, "Open"):
            return self.parse_open_workbook()

        # In sheet "...", treat range ... as table X.
        if self.at(TokenKind.KEYWORD, "In"):
            return self.parse_treat_range_as_table()

        # Set X to expr.
        if self.at(TokenKind.KEYWORD, "Set"):
            return self.parse_set_var()

        # Call result X.
        if self.at(TokenKind.KEYWORD, "Call"):
            return self.parse_call_result()

        # Add column ... to ... as expr.
        if self.at(TokenKind.KEYWORD, "Add"):
            return self.parse_add_column()

        # Filter X where condition.
        if self.at(TokenKind.KEYWORD, "Filter"):
            return self.parse_filter_table()

        # Export expr to "path".
        if self.at(TokenKind.KEYWORD, "Export"):
            return self.parse_export()

        # Use system "..." version "...".
        if self.at(TokenKind.KEYWORD, "Use"):
            return self.parse_use_system()

        # Log in as credential "..."
        if self.at(TokenKind.KEYWORD, "Log"):
            return self.parse_log_in_out()

        # Go to page "..."
        if self.at(TokenKind.KEYWORD, "Go"):
            return self.parse_go_to_page()

        # Enter "field" = expr.
        if self.at(TokenKind.KEYWORD, "Enter"):
            return self.parse_enter_field()

        # Click "element".
        if self.at(TokenKind.KEYWORD, "Click"):
            return self.parse_click()

        # Extract X from field "selector".
        if self.at(TokenKind.KEYWORD, "Extract"):
            return self.parse_extract()

        if self.at(TokenKind.NEWLINE):
            self.advance()
            return None
        if self.at(TokenKind.EOF):
            return None
        raise ParseError(
            f"Unexpected token: {t.kind} {t.value!r}. Expected a statement.",
            t.line, t.column, self.path,
        )

    def parse_for_each(self) -> ForEach:
        start = self.advance()  # For
        self.expect(TokenKind.KEYWORD, "each")
        if self.at(TokenKind.KEYWORD, "row"):
            self.advance()
            var = "row"
        else:
            var_t = self.expect(TokenKind.IDENT)
            var = var_t.value
        self.expect(TokenKind.KEYWORD, "in")
        collection = self.parse_expression()
        self.expect(TokenKind.COLON)
        self._skip_newlines()
        body: list[Statement] = []
        if self.at(TokenKind.INDENT):
            self.advance()
            while not self.at(TokenKind.DEDENT) and not self.at(TokenKind.EOF):
                s = self.parse_statement()
                if s is not None:
                    body.append(s)
                self._skip_newlines()
            if self.at(TokenKind.DEDENT):
                self.advance()
        return ForEach(var=var, collection=collection, body=body, loc=self.loc(start))

    def parse_open_workbook(self) -> OpenWorkbook:
        start = self.advance()
        self.expect(TokenKind.KEYWORD, "workbook")
        path_t = self.expect(TokenKind.STRING)
        self.expect(TokenKind.DOT)
        return OpenWorkbook(path=path_t.value, loc=self.loc(start))

    def parse_treat_range_as_table(self) -> TreatRangeAsTable:
        start = self.advance()  # In
        self.expect(TokenKind.KEYWORD, "sheet")
        sheet_t = self.expect(TokenKind.STRING)
        self.expect(TokenKind.COMMA)
        self.expect(TokenKind.KEYWORD, "treat")
        self.expect(TokenKind.KEYWORD, "range")
        range_t = self.expect(TokenKind.IDENT)  # or range literal A1:G999
        range_spec = range_t.value
        self.expect(TokenKind.KEYWORD, "as")
        self.expect(TokenKind.KEYWORD, "table")
        name_t = self.expect(TokenKind.IDENT)
        self.expect(TokenKind.DOT)
        return TreatRangeAsTable(
            sheet=sheet_t.value,
            range_spec=range_spec,
            table_name=name_t.value,
            loc=self.loc(start),
        )

    def parse_set_var(self) -> SetVar:
        start = self.advance()  # Set
        name_t = self.expect(TokenKind.IDENT)
        self.expect(TokenKind.KEYWORD, "to")
        value = self.parse_expression()
        self.expect(TokenKind.DOT)
        return SetVar(name=name_t.value, value=value, loc=self.loc(start))

    def parse_call_result(self) -> CallResult:
        start = self.advance()  # Call
        self.expect(TokenKind.KEYWORD, "result")
        name_t = self.expect(TokenKind.IDENT)
        self.expect(TokenKind.DOT)
        return CallResult(name=name_t.value, loc=self.loc(start))

    def parse_add_column(self) -> AddColumn:
        start = self.advance()  # Add
        self.expect(TokenKind.KEYWORD, "column")
        name_t = self.expect(TokenKind.IDENT)
        self.expect(TokenKind.KEYWORD, "to")
        table_t = self.expect(TokenKind.IDENT)
        self.expect(TokenKind.KEYWORD, "as")
        expr = self.parse_expression()
        self.expect(TokenKind.DOT)
        return AddColumn(
            table=table_t.value,
            name=name_t.value,
            expr=expr,
            loc=self.loc(start),
        )

    def parse_filter_table(self) -> FilterTable:
        start = self.advance()  # Filter
        table_t = self.expect(TokenKind.IDENT)
        self.expect(TokenKind.KEYWORD, "where")
        condition = self.parse_expression()
        self.expect(TokenKind.DOT)
        return FilterTable(table=table_t.value, condition=condition, loc=self.loc(start))

    def parse_export(self) -> ExportTable:
        start = self.advance()  # Export
        source = self.parse_expression()
        self.expect(TokenKind.KEYWORD, "to")
        path_t = self.expect(TokenKind.STRING)
        self.expect(TokenKind.DOT)
        return ExportTable(source=source, path=path_t.value, loc=self.loc(start))

    def parse_use_system(self) -> UseSystem:
        start = self.advance()  # Use
        self.expect(TokenKind.KEYWORD, "system")
        name_t = self.expect(TokenKind.STRING)
        self.expect(TokenKind.KEYWORD, "version")
        ver_t = self.expect(TokenKind.STRING)
        self.expect(TokenKind.DOT)
        return UseSystem(name=name_t.value, version=ver_t.value, loc=self.loc(start))

    def parse_log_in_out(self) -> Statement:
        start = self.advance()  # Log
        in_out = self.expect(TokenKind.KEYWORD)  # in or out
        if in_out.value == "out":
            self.expect(TokenKind.DOT)
            return LogOut(loc=self.loc(start))
        self.expect(TokenKind.KEYWORD, "as")
        self.expect(TokenKind.KEYWORD, "credential")
        cred_t = self.expect(TokenKind.STRING)
        self.expect(TokenKind.DOT)
        return LogIn(credential=cred_t.value, loc=self.loc(start))

    def parse_go_to_page(self) -> GoToPage:
        start = self.advance()  # Go
        self.expect(TokenKind.KEYWORD, "to")
        self.expect(TokenKind.KEYWORD, "page")
        page_t = self.expect(TokenKind.STRING)
        self.expect(TokenKind.DOT)
        return GoToPage(page=page_t.value, loc=self.loc(start))

    def parse_enter_field(self) -> EnterField:
        start = self.advance()  # Enter
        field_t = self.expect(TokenKind.STRING)
        self.expect(TokenKind.EQ)
        value = self.parse_expression()
        self.expect(TokenKind.DOT)
        return EnterField(field_id=field_t.value, value=value, loc=self.loc(start))

    def parse_click(self) -> ClickElement:
        start = self.advance()  # Click
        elem_t = self.expect(TokenKind.STRING)
        self.expect(TokenKind.DOT)
        return ClickElement(element_id=elem_t.value, loc=self.loc(start))

    def parse_extract(self) -> ExtractField:
        start = self.advance()  # Extract
        var_t = self.expect(TokenKind.IDENT)
        self.expect(TokenKind.KEYWORD, "from")
        kind = self.advance()
        if kind.value not in ("field", "element"):
            raise ParseError("Expected 'field' or 'element'", kind.line, kind.column, self.path)
        sel_t = self.expect(TokenKind.STRING)
        self.expect(TokenKind.DOT)
        return ExtractField(var_name=var_t.value, selector=sel_t.value, loc=self.loc(start))

    def _skip_newlines(self) -> None:
        while self.at(TokenKind.NEWLINE):
            self.advance()

    def parse_expression(self) -> Any:
        return self.parse_or()

    def parse_or(self) -> Any:
        left = self.parse_and()
        while self.at(TokenKind.KEYWORD, "or"):
            op_t = self.advance()
            right = self.parse_and()
            left = BinaryExpr(left=left, op="or", right=right, loc=self.loc(op_t))
        return left

    def parse_and(self) -> Any:
        left = self.parse_compare()
        while self.at(TokenKind.KEYWORD, "and"):
            op_t = self.advance()
            right = self.parse_compare()
            left = BinaryExpr(left=left, op="and", right=right, loc=self.loc(op_t))
        return left

    def parse_compare(self) -> Any:
        left = self.parse_additive()
        op = None
        if self.at(TokenKind.EQ):
            op_t = self.advance()
            op = CompOp.EQ
        elif self.at(TokenKind.GT):
            op_t = self.advance()
            op = CompOp.GT
        elif self.at(TokenKind.GTE):
            op_t = self.advance()
            op = CompOp.GE
        elif self.at(TokenKind.LT):
            op_t = self.advance()
            op = CompOp.LT
        elif self.at(TokenKind.LTE):
            op_t = self.advance()
            op = CompOp.LE
        elif self.at(TokenKind.NE):
            op_t = self.advance()
            op = CompOp.NE
        if op is not None:
            right = self.parse_additive()
            left = Comparison(left=left, op=op, right=right, loc=self.loc(self.tokens[self.pos - 1]))
        return left

    def parse_additive(self) -> Any:
        left = self.parse_term()
        while self.peek().kind in (TokenKind.KEYWORD,) and self.peek().value in ("+", "-") or (
            self.peek().kind == "KEYWORD" and self.peek().value in ("+", "-")
        ):
            # Simple: allow + - as tokens. Lexer doesn't emit KEYWORD for + - yet, so use IDENT or add PLUS/MINUS
            break
        return left

    def parse_term(self) -> Any:
        return self.parse_primary()

    def parse_primary(self) -> Any:
        t = self.peek()
        if self.at(TokenKind.NUMBER):
            self.advance()
            return NumberLit(value=t.value, loc=self.loc(t))
        if self.at(TokenKind.STRING):
            self.advance()
            return StringLit(value=t.value, loc=self.loc(t))
        # Only parse table.col or row.col when DOT is followed by IDENT (avoid eating sentence-ending ".")
        if self.at(TokenKind.KEYWORD, "row") and self.pos + 2 < len(self.tokens) and self.tokens[self.pos + 1].kind == TokenKind.DOT and self.tokens[self.pos + 2].kind == TokenKind.IDENT:
            self.advance()
            self.advance()  # DOT
            field_t = self.expect(TokenKind.IDENT)
            return QualifiedRef(base="row", field=field_t.value, loc=self.loc(t))
        # Money: IDENT/KEYWORD (USD/EUR/GBP) followed by NUMBER — must come before general IDENT
        if (self.at(TokenKind.KEYWORD) or self.at(TokenKind.IDENT)) and self.peek().value in ("USD", "EUR", "GBP"):
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].kind == TokenKind.NUMBER:
                curr_t = self.advance()
                amount_t = self.expect(TokenKind.NUMBER)
                return MoneyLit(currency=curr_t.value, amount=float(amount_t.value), loc=self.loc(t))
        if self.at(TokenKind.KEYWORD, "date"):
            self.advance()
            date_t = self.expect(TokenKind.STRING)
            return DateLit(value=date_t.value, loc=self.loc(t))
        if self.at(TokenKind.IDENT):
            self.advance()
            name = t.value
            if self.at(TokenKind.DOT) and self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].kind == TokenKind.IDENT:
                self.advance()
                field_t = self.expect(TokenKind.IDENT)
                return QualifiedRef(base=name, field=field_t.value, loc=self.loc(t))
            return Identifier(name=name, loc=self.loc(t))
        if self.at(TokenKind.LPAREN):
            self.advance()
            expr = self.parse_expression()
            self.expect(TokenKind.RPAREN)
            return expr
        raise ParseError(f"Expected expression, got {t.kind} {t.value!r}", t.line, t.column, self.path)


def parse(source: str, path: Optional[str] = None) -> Program:
    """Parse EAC source into a Program AST."""
    tokens = tokenize(source, path)
    parser = Parser(tokens, path)
    return parser.parse_program()
