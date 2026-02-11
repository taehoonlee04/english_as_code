"""
EAC Web Editor backend. Serves API for run, check, templates, and AI authoring.
Run from repo root: python -m editor.backend.main  (or uvicorn editor.backend.main:app --reload)
"""

import json
import os
import re
import sys
from pathlib import Path

# Ensure repo root is on path so we can import eac
_repo_root = Path(__file__).resolve().parent.parent.parent
_editor_dir = Path(__file__).resolve().parent.parent
_fixtures_dir = _editor_dir / "fixtures"
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
_src = _repo_root / "src"
if _src.exists() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Load .env from repo root or editor/ so OPENAI_API_KEY etc. can be set there
try:
    from dotenv import load_dotenv
    for d in (_repo_root, Path(__file__).resolve().parent.parent):
        load_dotenv(d / ".env")
except ImportError:
    pass

import yaml
from fastapi import FastAPI, HTTPException, UploadFile, File as FastAPIFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from eac.errors import EACError, ParseError, TypeCheckError
from eac.lowering import lower
from eac.parser import parse
from eac.runtime.interpreter import run
from eac.type_checker import check

app = FastAPI(title="EAC Editor API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- Request/response models ---

class SourceRequest(BaseModel):
    source: str


class RunResponse(BaseModel):
    ok: bool
    message: str
    trace: list[dict] | None = None
    error: str | None = None


class CheckResponse(BaseModel):
    ok: bool
    error: str | None = None


class TemplatesResponse(BaseModel):
    templates: dict


class AIAuthorRequest(BaseModel):
    prompt: str
    retry_on_parse_error: bool = True
    max_retries: int = 2


class AIAuthorResponse(BaseModel):
    ok: bool
    source: str | None = None
    error: str | None = None
    parse_error: str | None = None


class UploadResponse(BaseModel):
    ok: bool
    filename: str
    size: int
    path: str


class FileInfo(BaseModel):
    name: str
    size: int
    path: str


class FilesResponse(BaseModel):
    files: list[FileInfo]


ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

# JSON schema for OpenAI structured output — the LLM returns steps in this format
# instead of raw EAC text, so we can deterministically assemble valid syntax.
EAC_STEPS_SCHEMA = {
    "name": "eac_steps",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "anyOf": [
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["open_workbook"]},
                                "path": {"type": "string"},
                            },
                            "required": ["op", "path"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["treat_range"]},
                                "sheet": {"type": "string"},
                                "range": {"type": "string"},
                                "table": {"type": "string"},
                            },
                            "required": ["op", "sheet", "range", "table"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["set_var"]},
                                "var": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["op", "var", "value"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["call_result"]},
                                "id": {"type": "string"},
                            },
                            "required": ["op", "id"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["add_column"]},
                                "col": {"type": "string"},
                                "table": {"type": "string"},
                                "expr": {"type": "string"},
                            },
                            "required": ["op", "col", "table", "expr"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["filter"]},
                                "table": {"type": "string"},
                                "condition": {"type": "string"},
                            },
                            "required": ["op", "table", "condition"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["sort"]},
                                "table": {"type": "string"},
                                "by": {"type": "string"},
                                "dir": {"type": "string", "enum": ["ascending", "descending"]},
                            },
                            "required": ["op", "table", "by", "dir"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["export"]},
                                "expr": {"type": "string"},
                                "path": {"type": "string"},
                            },
                            "required": ["op", "expr", "path"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "enum": ["comment"]},
                                "text": {"type": "string"},
                            },
                            "required": ["op", "text"],
                            "additionalProperties": False,
                        },
                    ]
                },
            }
        },
        "required": ["steps"],
        "additionalProperties": False,
    },
}


def _serializable_trace(trace: list[dict]) -> list[dict]:
    """Replace non-JSON-serializable values in trace (e.g. openpyxl Workbook) so FastAPI can return it."""
    def sanitize(v):
        if v is None or isinstance(v, (bool, int, float, str)):
            return v
        if isinstance(v, (tuple, list)):
            return [sanitize(x) for x in v]
        if isinstance(v, dict):
            return {k: sanitize(x) for k, x in v.items()}
        try:
            from datetime import date, datetime
            if isinstance(v, (date, datetime)):
                return str(v)
        except ImportError:
            pass
        return f"<{type(v).__name__}>"
    return [sanitize(entry) for entry in trace]


# --- Mock data for default sample program (aging report) ---

def _ensure_mock_data() -> None:
    """Create editor/fixtures/data/accounts_receivable.xlsx and output/ if missing so the sample program runs."""
    data_dir = _fixtures_dir / "data"
    output_dir = _fixtures_dir / "output"
    xlsx_path = data_dir / "accounts_receivable.xlsx"
    if xlsx_path.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        return
    try:
        import openpyxl
    except ImportError:
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Open Items"
    # A1:G1 headers; program uses OpenItems.Balance and exports
    headers = ["Customer", "InvoiceNo", "Amount", "Balance", "DueDate", "Status", "Notes"]
    ws.append(headers)
    ws.append(["Acme Corp", "INV-001", 1000.0, 150.0, "2026-01-15", "Open", "Overdue"])
    ws.append(["Beta Inc", "INV-002", 500.0, 0.0, "2026-02-01", "Paid", ""])
    ws.append(["Gamma LLC", "INV-003", 750.0, 75.5, "2026-02-10", "Open", ""])
    ws.append(["Delta Co", "INV-004", 200.0, 200.0, "2026-02-05", "Open", ""])
    wb.save(xlsx_path)


# --- Load grammar/templates for AI context ---

def _load_templates() -> dict:
    path = _repo_root / "grammar" / "sentence_templates.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _templates_for_prompt() -> str:
    data = _load_templates()
    lines = ["# EAC sentence patterns (use these exact forms):"]
    for category, items in data.items():
        if isinstance(items, list):
            lines.append(f"\n## {category}")
            for item in items:
                lines.append(f"  - {item}")
        elif isinstance(items, dict):
            lines.append(f"\n## {category}")
            for k, v in items.items():
                if isinstance(v, list):
                    for item in v:
                        lines.append(f"  - {item}")
                else:
                    lines.append(f"  - {v}")
    return "\n".join(lines)


# --- API routes ---

@app.post("/api/check", response_model=CheckResponse)
def api_check(req: SourceRequest) -> CheckResponse:
    """Parse and type-check source. Returns ok or error message."""
    try:
        program = parse(req.source, path="editor")
        check(program)
        return CheckResponse(ok=True)
    except ParseError as e:
        return CheckResponse(ok=False, error=str(e))
    except TypeCheckError as e:
        return CheckResponse(ok=False, error=str(e))
    except EACError as e:
        return CheckResponse(ok=False, error=str(e))
    except Exception as e:
        return CheckResponse(ok=False, error=str(e))


@app.post("/api/run", response_model=RunResponse)
def api_run(req: SourceRequest) -> RunResponse:
    """Parse, type-check, lower, and run. Uses editor/fixtures as cwd so data/ and output/ paths resolve to mock data."""
    try:
        _ensure_mock_data()
        program = parse(req.source, path="editor")
        check(program)
        ir = lower(program)
        old_cwd = os.getcwd()
        try:
            os.chdir(_fixtures_dir)
            trace = run(ir, dry_run=False, trace_path=None)
        finally:
            os.chdir(old_cwd)
        return RunResponse(ok=True, message=f"Completed {len(trace)} steps.", trace=_serializable_trace(trace))
    except ParseError as e:
        return RunResponse(ok=False, message=str(e), error=str(e))
    except TypeCheckError as e:
        return RunResponse(ok=False, message=str(e), error=str(e))
    except EACError as e:
        return RunResponse(ok=False, message=str(e), error=str(e))
    except Exception as e:
        return RunResponse(ok=False, message=str(e), error=str(e))


@app.get("/api/templates", response_model=TemplatesResponse)
def api_templates() -> TemplatesResponse:
    """Return sentence templates for the step wizard and AI context."""
    return TemplatesResponse(templates=_load_templates())


@app.get("/api/grammar-prompt")
def api_grammar_prompt() -> str:
    """Return text suitable for inclusion in an LLM prompt (EAC patterns)."""
    return _templates_for_prompt()


def _assemble_eac_line(step: dict) -> str:
    """Deterministic template for each op type. Mirrors frontend's getStepLine() at app.js:690-712."""
    op = step.get("op", "")
    if op == "open_workbook":
        return f'Open workbook "{step["path"]}".'
    elif op == "treat_range":
        return f'In sheet "{step["sheet"]}", treat range {step["range"]} as table {step["table"]}.'
    elif op == "set_var":
        return f'Set {step["var"]} to {step["value"]}.'
    elif op == "call_result":
        return f'Call result {step["id"]}.'
    elif op == "add_column":
        return f'Add column {step["col"]} to {step["table"]} as {step["expr"]}.'
    elif op == "filter":
        return f'Filter {step["table"]} where {step["condition"]}.'
    elif op == "sort":
        direction = step.get("dir", "ascending")
        if direction not in ("ascending", "descending"):
            direction = "ascending"
        return f'Sort {step["table"]} by {step["by"]} {direction}.'
    elif op == "export":
        return f'Export {step["expr"]} to "{step["path"]}".'
    elif op == "comment":
        return f'-- {step["text"]}'
    else:
        return f'-- unknown op: {op}'


def _assemble_eac(steps: list[dict]) -> str:
    """Assemble structured steps into EAC source text."""
    return "\n".join(_assemble_eac_line(step) for step in steps)


def _build_json_system_prompt() -> str:
    """Build system prompt that teaches the LLM to produce structured JSON steps instead of raw EAC."""
    return (
        "You are an assistant that converts natural-language descriptions into structured JSON "
        "representing an English-as-Code (EAC) program.\n\n"
        "Output a JSON object with a single key \"steps\", whose value is an array of step objects.\n"
        "Each step has an \"op\" field and additional fields depending on the op:\n\n"
        "| op             | fields                        | notes                                        |\n"
        "| open_workbook  | path                          | file path, no quotes (e.g. data/file.xlsx)   |\n"
        "| treat_range    | sheet, range, table           | table is an identifier (no spaces)           |\n"
        "| set_var        | var, value                    | var is identifier; value is EAC expression   |\n"
        "| call_result    | id                            | identifier                                   |\n"
        "| add_column     | col, table, expr              | col is identifier; expr is EAC expression    |\n"
        "| filter         | table, condition              | condition is EAC expression                  |\n"
        "| sort           | table, by, dir                | dir must be \"ascending\" or \"descending\"      |\n"
        "| export         | expr, path                    | expr is usually a table name                 |\n"
        "| comment        | text                          | for comments                                 |\n\n"
        "Rules:\n"
        "- path and sheet are raw strings (no quotes — templates add them)\n"
        "- table, var, col, id must be valid identifiers: letters, digits, underscores, no spaces\n"
        "- value, expr, condition, by use EAC expression syntax:\n"
        "  - Column references: TableName.ColumnName (e.g. Invoices.Balance)\n"
        "  - Currency literals: USD 100.00, EUR 50.00\n"
        "  - Date literals: date \"2026-01-15\"\n"
        "  - Comparisons: >, <, >=, <=, =\n"
        "  - Arithmetic: +, -, *, /\n"
        "- range uses formats like A1:G999 or A1G999\n\n"
        "Example — user asks \"open accounts_receivable.xlsx, filter items with balance over zero, "
        "export to CSV\":\n"
        "{\n"
        '  "steps": [\n'
        '    {"op": "open_workbook", "path": "data/accounts_receivable.xlsx"},\n'
        '    {"op": "treat_range", "sheet": "Sheet1", "range": "A1:G999", "table": "Items"},\n'
        '    {"op": "filter", "table": "Items", "condition": "Items.Balance > USD 0.00"},\n'
        '    {"op": "export", "expr": "Items", "path": "output/result.csv"}\n'
        "  ]\n"
        "}\n\n"
        "Output ONLY the JSON object. No explanation or markdown."
    )


def _call_llm_for_eac_json(prompt: str, parse_error: str | None = None) -> list[dict]:
    """Call OpenAI API with structured JSON output to get EAC steps."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("AI authoring requires: pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")  # optional, for local models
    if not api_key and not base_url:
        raise RuntimeError("Set OPENAI_API_KEY (or OPENAI_BASE_URL) for AI authoring.")
    client = OpenAI(api_key=api_key or "not-needed", base_url=base_url) if base_url else OpenAI()

    system = _build_json_system_prompt()
    user_content = f"User request: {prompt}"
    if parse_error:
        user_content += (
            f"\n\nThe previous attempt produced EAC that failed to parse with this error:\n"
            f"{parse_error}\n"
            f"Please adjust the steps to fix the issue."
        )

    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        response_format={
            "type": "json_schema",
            "json_schema": EAC_STEPS_SCHEMA,
        },
    )

    text = response.choices[0].message.content if response.choices else None
    if not text or not text.strip():
        raise RuntimeError("Model returned empty content. Try a different model or prompt.")

    data = json.loads(text)
    return data.get("steps", [])


@app.post("/api/ai-author", response_model=AIAuthorResponse)
def api_ai_author(req: AIAuthorRequest) -> AIAuthorResponse:
    """Generate EAC from natural language using structured JSON output, then assemble into valid EAC."""
    parse_error = None
    for attempt in range(req.max_retries + 1):
        try:
            steps = _call_llm_for_eac_json(req.prompt, parse_error=parse_error)
            source = _assemble_eac(steps)
        except Exception as e:
            return AIAuthorResponse(ok=False, error=str(e))
        try:
            program = parse(source, path="editor")
            check(program)
            return AIAuthorResponse(ok=True, source=source)
        except (ParseError, TypeCheckError, EACError) as e:
            parse_error = str(e)
            if not req.retry_on_parse_error or attempt >= req.max_retries:
                return AIAuthorResponse(ok=False, source=source, parse_error=parse_error)
        except Exception as e:
            return AIAuthorResponse(ok=False, source=source, error=str(e))
    return AIAuthorResponse(ok=False, error="Unexpected error")


# --- File upload endpoints ---

@app.post("/api/upload", response_model=UploadResponse)
async def api_upload(file: UploadFile = FastAPIFile(...)) -> UploadResponse:
    """Accept a spreadsheet upload, validate extension, save to fixtures/data/."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB.")
    # Sanitize filename: keep only safe characters
    stem = re.sub(r'[^\w\-.]', '_', Path(file.filename).stem)
    safe_name = stem + ext
    data_dir = _fixtures_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / safe_name
    # Deduplicate with numeric suffix
    counter = 1
    while dest.exists():
        dest = data_dir / f"{stem}_{counter}{ext}"
        safe_name = dest.name
        counter += 1
    dest.write_bytes(data)
    return UploadResponse(ok=True, filename=safe_name, size=len(data), path=f"data/{safe_name}")


@app.get("/api/files", response_model=FilesResponse)
def api_files() -> FilesResponse:
    """List files in fixtures/data/."""
    data_dir = _fixtures_dir / "data"
    if not data_dir.exists():
        return FilesResponse(files=[])
    files = []
    for f in sorted(data_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS:
            files.append(FileInfo(name=f.name, size=f.stat().st_size, path=f"data/{f.name}"))
    return FilesResponse(files=files)


@app.delete("/api/files/{filename}")
def api_delete_file(filename: str):
    """Delete a file from fixtures/data/."""
    data_dir = _fixtures_dir / "data"
    target = data_dir / filename
    # Prevent path traversal
    if not target.resolve().parent == data_dir.resolve():
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    target.unlink()
    return {"ok": True}


# --- Static frontend ---

frontend_path = Path(__file__).resolve().parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
