# conftest.py - pytest configuration for cfmm2bids tests

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up the test environment."""
    # Ensure we're running from the repository root
    repo_root = Path(__file__).parent.parent.parent.parent
    os.chdir(repo_root)
    yield
