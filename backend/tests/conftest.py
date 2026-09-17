import os
from pathlib import Path

os.environ["MOCK_AZURE"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test-leavenow.db"

TEST_DATABASE = Path("data/test-leavenow.db")
if TEST_DATABASE.exists():
    TEST_DATABASE.unlink()
