import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_test_dir = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///' + str(Path(_test_dir.name) / 'test.db')
os.environ['JWT_SECRET'] = 'test-only-secret-with-at-least-32-characters'
os.environ['DEMO_MODE'] = 'true'
