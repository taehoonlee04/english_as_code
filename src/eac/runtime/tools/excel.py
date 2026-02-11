"""Excel/workbook tools. Deterministic: pinned locale, explicit paths."""

from pathlib import Path
from typing import Any


def excel_open_workbook(path: str, **kwargs: Any) -> Any:
    """Open a workbook; return a handle for subsequent read_table calls."""
    # Stub: in real impl load with openpyxl/pandas
    return {"path": path, "open": True}


def excel_read_table(
    workbook: str | dict,
    sheet: str,
    range_spec: str,
    **kwargs: Any,
) -> Any:
    """Read a range as a table (list of dicts)."""
    # Stub: return empty table
    return []


def excel_export(source: Any, path: str, **kwargs: Any) -> None:
    """Export table/data to CSV or XLSX."""
    # Stub: no-op
    pass
