import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def prev_xml() -> bytes:
    return (FIXTURES / "info_table_prev.xml").read_bytes()


@pytest.fixture
def curr_xml() -> bytes:
    return (FIXTURES / "info_table_curr.xml").read_bytes()


@pytest.fixture
def submissions() -> dict:
    return json.loads((FIXTURES / "submissions.json").read_text())
