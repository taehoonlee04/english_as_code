# EAC Web Editor

Minimal web editor for English-as-Code: edit EAC, run, add steps via wizard, and generate EAC from plain English (AI authoring).

## Run the editor

From the **repo root** (parent of `editor/`):

```bash
# Install editor dependencies (FastAPI, uvicorn, openai)
pip install -e ".[editor]"

# Start the server (serves API + frontend on http://localhost:8000)
# Use PYTHONPATH so the backend can import the eac package from src/
# If port 8000 is in use, set PORT=8001 (or stop the other process)
PYTHONPATH=src python -m editor.backend.main
```

Or with uvicorn (and optional port):

```bash
PYTHONPATH=src uvicorn editor.backend.main:app --reload --host 0.0.0.0 --port ${PORT:-8000}
```

Then open http://localhost:8000 in a browser.

The default sample program (aging report) runs against **mock data**: the backend creates `editor/fixtures/data/accounts_receivable.xlsx` on first run and uses `editor/fixtures/` as the working directory, so paths like `data/accounts_receivable.xlsx` and `output/aging_summary.csv` resolve there. Exported files appear under `editor/fixtures/output/`.

## Features

- **EAC source** — Edit your program in the left panel.
- **Check** — Parse and type-check (no execution).
- **Run** — Parse, type-check, lower, and execute. Output and trace appear in the right panel. (File outputs like Excel/CSV are written to the server’s current working directory.)
- **Add step** — Wizard: pick a sentence type (Open workbook, Treat range, Set variable, Add column, Filter, Export), fill the form, and insert the line into the source.
- **Generate from description** — AI authoring: describe what you want in plain English; the app calls an LLM and inserts draft EAC. Parser is used to validate; on failure you see the error (and the backend can retry with the error in the prompt).

## AI authoring (optional)

“Generate from description” calls an OpenAI-compatible API. Configure it in one of these ways:

### Option 1: OpenAI API key

1. Get a key: [OpenAI API keys](https://platform.openai.com/api-keys) (sign in, create key).
2. Set it when starting the server:
   ```bash
   export OPENAI_API_KEY=sk-your-key-here
   PYTHONPATH=src python -m editor.backend.main
   ```
   Or put it in a `.env` file in the repo root or in `editor/` (no quotes, no spaces):
   ```
   OPENAI_API_KEY=sk-your-key-here
   ```
   The backend loads `.env` automatically if `python-dotenv` is installed (it is with `.[editor]`).

Optional: `OPENAI_MODEL=gpt-4o` (default is `gpt-4o-mini`).

### Option 2: Local or custom endpoint (OPENAI_BASE_URL)

Use this for a server that speaks the OpenAI API (same request/response shape):

- **Ollama** (local models): run `ollama serve`, then:
  ```bash
  export OPENAI_BASE_URL=http://localhost:11434/v1
  export OPENAI_MODEL=llama3.2
  PYTHONPATH=src python -m editor.backend.main
  ```
  No API key needed; Ollama ignores it.

- **Azure OpenAI**: set `OPENAI_BASE_URL` to your endpoint (e.g. `https://your-resource.openai.azure.com/openai/deployments/your-deployment`) and `OPENAI_API_KEY` to your Azure key.

- **Other** (LiteLLM, OpenRouter, etc.): set `OPENAI_BASE_URL` and `OPENAI_API_KEY` as that service requires.

If neither `OPENAI_API_KEY` nor `OPENAI_BASE_URL` is set, “Generate from description” returns an error asking you to set one.

## Project layout

- `editor/backend/main.py` — FastAPI app: `/api/check`, `/api/run`, `/api/templates`, `/api/ai-author`, `/api/grammar-prompt`; serves static frontend at `/`.
- `editor/frontend/` — Static HTML/JS: `index.html`, `app.js`.
