"""
EAC Web Editor backend. Serves API for run, check, templates, and AI authoring.
Run from repo root: python -m editor.backend.main  (or uvicorn editor.backend.main:app --reload)
"""

import os
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
from fastapi import FastAPI, HTTPException
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


def _call_llm_for_eac(prompt: str, parse_error: str | None = None) -> str:
    """Call OpenAI-compatible API to generate EAC. Uses OPENAI_API_KEY or OPENAI_BASE_URL."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("AI authoring requires: pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")  # optional, for local models
    if not api_key and not base_url:
        raise RuntimeError("Set OPENAI_API_KEY (or OPENAI_BASE_URL) for AI authoring.")
    client = OpenAI(api_key=api_key or "not-needed", base_url=base_url) if base_url else OpenAI()
    grammar_block = _templates_for_prompt()
    system = (
        "You are a helpful assistant that produces English-as-Code (EAC) programs. "
        "Output ONLY valid EAC code, no explanation. Use exactly the sentence patterns below. "
        "One statement per line. End each statement with a period. "
        "Rules: Use 'Set X to expr.' (with 'to'), never 'Set X as expr.'. "
        "Table names and variable names are identifiers (no quotes). "
        "Range can be A1:J100. Column refs: TableName.ColumnName (e.g. InvoicesTable.Balance)."
    )
    user_content = f"{grammar_block}\n\n---\n\nUser request: {prompt}"
    if parse_error:
        user_content += f"\n\nPrevious attempt failed with this error. Fix the EAC output:\n{parse_error}"
    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
    )
    text = response.choices[0].message.content if response.choices else None
    if not text or not text.strip():
        raise RuntimeError("Model returned empty content. Try a different model or prompt.")
    text = text.strip()
    # Strip markdown code block if present
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _normalize_generated_eac(raw: str) -> str:
    """Normalize common LLM output so it parses: strip bullets, semicolons -> periods, fix 'as X' -> 'as table X', turn section headers into comments."""
    lines = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("- ") or s.startswith("* ") or s.startswith("• "):
            s = s[2:].strip()
        if s.endswith(";"):
            s = s[:-1].rstrip() + "."
        if "treat range " in s.lower() and " as table " not in s and " as " in s:
            s = s.replace(" as ", " as table ", 1)
        if s.strip().lower().startswith("set ") and " as " in s and " to " not in s:
            s = s.replace(" as ", " to ", 1)
        if s.lower().startswith("define "):
            s = "-- " + s
        elif s and not s.endswith(".") and not s.rstrip().endswith('"'):
            s = "-- " + s
        lines.append(s)
    return "\n".join(lines)


@app.post("/api/ai-author", response_model=AIAuthorResponse)
def api_ai_author(req: AIAuthorRequest) -> AIAuthorResponse:
    """Generate EAC from natural language. Uses parser as validator; optionally retries with error feedback."""
    parse_error = None
    for attempt in range(req.max_retries + 1):
        try:
            raw = _call_llm_for_eac(req.prompt, parse_error=parse_error)
            source = _normalize_generated_eac(raw)
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


# --- Static frontend ---

frontend_path = Path(__file__).resolve().parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
