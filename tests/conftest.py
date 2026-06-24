import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_cropverse.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-cropverse")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("REDIS_URL", "")

from main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
