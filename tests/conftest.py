import os
import sys

import pytest

# Make the repo root importable so `import redbook_parser` works from tests.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def detail_lines():
    """A canonical detail-page line stream: code+desc line, 6 amount lines."""
    return [
        "111111 अर्थ मन्त्रालय कार्यालय",
        "1,000",
        "2,000",
        "3,000",
        "4,000",
        "5,000",
        "6,000",
    ]
