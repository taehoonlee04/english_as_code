# English as Code (EAC)

A Controlled Natural Language (CNL) for white-collar automation: spreadsheets (Excel-like) and web ERP workflows. Write in near-English; run deterministically.

## Vision

Open a text file, write what you want in EAC, run it. AI can help you author and debug. The language compiles to a deterministic IR; the runtime (or a future agent) executes the IR, not raw text.

## Quick Start

```bash
# Install (adds 'eac' command)
pip install -e .

# Parse and show AST
eac parse tests/examples/aging_report.eac

# Type-check
eac check tests/examples/aging_report.eac

# Emit IR JSON
eac lower tests/examples/aging_report.eac

# Run (or dry-run)
eac run tests/examples/aging_report.eac --dry-run
```

Without installing, from project root:

```bash
PYTHONPATH=src python3 -c "
from eac.parser import parse
from eac.lowering import lower
from eac.runtime.interpreter import run
prog = parse(open('tests/examples/aging_report.eac').read())
run(lower(prog), dry_run=True)
"
```

## Project Structure

- **grammar/** — EBNF grammar, keywords, sentence templates
- **src/eac/** — Lexer, parser, type checker, IR lowering, runtime, CLI
- **tests/examples/** — Example `.eac` programs

## Commands (CLI)

- `eac parse <file.eac>` — Parse and show AST
- `eac check <file.eac>` — Type check
- `eac lower <file.eac>` — Emit IR JSON
- `eac run <file.eac>` — Execute
- `eac explain <file.eac>` — IR to plain English summary

## Requirements

- Python 3.12+

## Development and testing (venv)

Create a virtualenv, install the package with dev dependencies, and run tests:

```bash
# One-liner
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest tests/ -v

# Or use the script
./scripts/setup_venv.sh
```

Then use the venv for commands:

```bash
.venv/bin/eac parse tests/examples/aging_report.eac
.venv/bin/pytest tests/ -v
```

## License

MIT (or your choice)
