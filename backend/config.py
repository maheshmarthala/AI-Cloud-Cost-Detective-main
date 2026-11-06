import os
from dotenv import load_dotenv

load_dotenv()
DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'
JWT_SECRET = os.getenv('JWT_SECRET', '')
if len(JWT_SECRET) < 32:
    raise RuntimeError('Set JWT_SECRET to a random secret of at least 32 characters.')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./detective.db')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',')
