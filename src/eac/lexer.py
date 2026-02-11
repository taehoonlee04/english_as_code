"""Tokenizer for EAC: CNL source -> tokens with keyword recognition and indentation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from eac.errors import ParseError


class TokenKind:
    # Literals
    NUMBER = "NUMBER"
    STRING = "STRING"
    IDENT = "IDENT"
    # Keywords (stored with kind KEYWORD, value = word)
    KEYWORD = "KEYWORD"
    # Punctuation / structure
    DOT = "DOT"
    COMMA = "COMMA"
    COLON = "COLON"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    EQ = "EQ"
    GT = "GT"
    LT = "LT"
    GTE = "GTE"
    LTE = "LTE"
    NE = "NE"
    NEWLINE = "NEWLINE"
    INDENT = "INDENT"
    DEDENT = "DEDENT"
    EOF = "EOF"


@dataclass
class Token:
    kind: str
    value: Any
    line: int
    column: int

    def __repr__(self) -> str:
        return f"Token({self.kind}, {self.value!r}, L{self.line}:{self.column})"


def load_keywords() -> set[str]:
    grammar_dir = Path(__file__).resolve().parent.parent.parent / "grammar"
    keywords_yaml = grammar_dir / "keywords.yaml"
    if keywords_yaml.exists():
        try:
            import yaml
            with open(keywords_yaml) as f:
                data = yaml.safe_load(f)
            keywords = set()
            for section in ("verbs", "types", "special"):
                if section in data and data[section]:
                    keywords.update(w for w in data[section] if isinstance(w, str))
            return keywords
        except Exception:
            pass
    # Fallback when yaml not installed or file missing
    return {
        "Open", "workbook", "In", "sheet", "treat", "range", "as", "table", "Set", "to",
        "Add", "column", "Filter", "where", "Export", "Use", "system", "version", "Log",
        "in", "out", "credential", "Go", "page", "Enter", "Click", "Extract", "from",
        "field", "element", "For", "each", "Call", "result", "date", "row",
    }


_KEYWORDS: Optional[set[str]] = None


def get_keywords() -> set[str]:
    global _KEYWORDS
    if _KEYWORDS is None:
        _KEYWORDS = load_keywords()
    return _KEYWORDS


def tokenize(source: str, path: Optional[str] = None) -> list[Token]:
    """Produce a list of tokens from EAC source. Tracks indentation (Python-style)."""
    keywords = get_keywords()
    tokens: list[Token] = []
    lines = source.split("\n")
    indent_stack = [0]
    i = 0
    line_no = 1
    col = 0

    def advance() -> Optional[str]:
        nonlocal i, col, line_no
        if i >= len(source):
            return None
        c = source[i]
        i += 1
        if c == "\n":
            col = 0
            line_no += 1
        else:
            col += 1
        return c

    def peek() -> Optional[str]:
        if i >= len(source):
            return None
        return source[i]

    def skip_whitespace_line() -> bool:
        """Skip spaces on current line; return True if we hit newline (line is blank)."""
        nonlocal i, col
        while i < len(source) and source[i] in " \t":
            i += 1
            col += 1
        return i < len(source) and source[i] == "\n"

    def read_comment() -> None:
        nonlocal i, col, line_no
        # "--" already consumed; skip rest of line
        while i < len(source) and source[i] != "\n":
            i += 1
            col += 1
        if i < len(source):
            advance()  # consume newline
            line_no += 1
            col = 0

    while i < len(source):
        # Skip spaces
        while i < len(source) and source[i] in " \t" and source[i] != "\n":
            advance()

        if i >= len(source):
            break

        line_start = col
        c = source[i]

        if c == "\n":
            tokens.append(Token(TokenKind.NEWLINE, "\n", line_no, col))
            advance()
            continue

        if c == "-" and peek() and source[i + 1] == "-":
            advance()
            advance()
            col -= 2  # report start of comment
            read_comment()
            continue

        # Indentation (at line start)
        if col == 0 and c in " \t":
            spaces = 0
            while i < len(source) and source[i] in " \t":
                if source[i] == "\t":
                    spaces += 4  # treat tab as 4 spaces
                else:
                    spaces += 1
                advance()
            if i < len(source) and source[i] == "\n":
                continue  # blank line
            while indent_stack and spaces < indent_stack[-1]:
                indent_stack.pop()
                tokens.append(Token(TokenKind.DEDENT, None, line_no, 0))
            if indent_stack and spaces > indent_stack[-1]:
                indent_stack.append(spaces)
                tokens.append(Token(TokenKind.INDENT, None, line_no, 0))
            continue

        # Punctuation
        if c == ".":
            tokens.append(Token(TokenKind.DOT, ".", line_no, col))
            advance()
            continue
        if c == ",":
            tokens.append(Token(TokenKind.COMMA, ",", line_no, col))
            advance()
            continue
        if c == ":":
            tokens.append(Token(TokenKind.COLON, ":", line_no, col))
            advance()
            continue
        if c == "(":
            tokens.append(Token(TokenKind.LPAREN, "(", line_no, col))
            advance()
            continue
        if c == ")":
            tokens.append(Token(TokenKind.RPAREN, ")", line_no, col))
            advance()
            continue
        if c == "=":
            if peek() == "=":
                advance()
                advance()
                tokens.append(Token(TokenKind.EQ, "=", line_no, col))
            else:
                tokens.append(Token(TokenKind.EQ, "=", line_no, col))
                advance()
            continue
        if c == ">" and peek() == "=":
            advance()
            advance()
            tokens.append(Token(TokenKind.GTE, ">=", line_no, col))
            continue
        if c == ">":
            tokens.append(Token(TokenKind.GT, ">", line_no, col))
            advance()
            continue
        if c == "<" and peek() == "=":
            advance()
            advance()
            tokens.append(Token(TokenKind.LTE, "<=", line_no, col))
            continue
        if c == "<":
            tokens.append(Token(TokenKind.LT, "<", line_no, col))
            advance()
            continue
        if c == "!" and peek() == "=":
            advance()
            advance()
            tokens.append(Token(TokenKind.NE, "!=", line_no, col))
            continue

        # String literal "..."
        if c == '"':
            advance()
            start = i
            while i < len(source) and source[i] != '"':
                if source[i] == "\\":
                    advance()
                advance()
            value = source[start:i]
            if i < len(source):
                advance()  # closing "
            tokens.append(Token(TokenKind.STRING, value, line_no, col))
            continue

        # Number (allow one decimal point; do not consume trailing "." so "1." -> NUMBER then DOT)
        if c.isdigit() or (c == "." and peek() and str(peek()).isdigit()):
            start = i
            seen_dot = False
            while i < len(source):
                ch = source[i]
                if ch == ".":
                    if seen_dot:
                        break
                    # Only consume "." if it is followed by a digit (e.g. "1.5")
                    if i + 1 >= len(source) or not source[i + 1].isdigit():
                        break
                    seen_dot = True
                    advance()
                elif ch.isdigit():
                    advance()
                else:
                    break
            num_str = source[start:i]
            try:
                value = float(num_str) if "." in num_str else int(num_str)
            except ValueError:
                raise ParseError(f"Invalid number: {num_str}", line_no, col, path)
            tokens.append(Token(TokenKind.NUMBER, value, line_no, col))
            continue

        # Identifier or keyword
        if c.isalpha() or c == "_":
            start = i
            while i < len(source) and (source[i].isalnum() or source[i] == "_"):
                advance()
            word = source[start:i]
            if word in keywords:
                tokens.append(Token(TokenKind.KEYWORD, word, line_no, col))
            else:
                tokens.append(Token(TokenKind.IDENT, word, line_no, col))
            continue

        advance()
        raise ParseError(f"Unexpected character: {c!r}", line_no, col, path)

    # Emit DEDENTs for remaining stack
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token(TokenKind.DEDENT, None, line_no, col))

    tokens.append(Token(TokenKind.EOF, None, line_no, col))
    return tokens
