"""Shared pytest fixtures (Context7-style)."""

import pytest
from pathlib import Path


@pytest.fixture
def examples_dir():
    """Path to tests/examples/ containing .eac files."""
    return Path(__file__).parent / "examples"


@pytest.fixture(params=["aging_report.eac", "erp_invoice_post.eac", "reconciliation.eac"])
def example_file(examples_dir, request):
    """Parametrized: one of the three example .eac programs."""
    return examples_dir / request.param
