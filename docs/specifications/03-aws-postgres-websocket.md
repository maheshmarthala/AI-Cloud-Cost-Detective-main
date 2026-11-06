# Prompt 3: Amazon RDS PostgreSQL + WebSocket Progress Tracking

Build on top of the existing FastAPI backend. Add Amazon RDS for PostgreSQL for storing users and analysis history, and FastAPI WebSocket for live progress updates.

## What to build

### Database (Amazon RDS for PostgreSQL)

- Connect to an Amazon RDS for PostgreSQL instance using `asyncpg` or `psycopg2`.
- Store the database connection string in `.env` (`DATABASE_URL`). Ensure the RDS security group allows inbound 5432 from your IP, and use `sslmode=require`.
- Create two tables on startup:
  - `users` — id, email, password_hash, created_at
  - `analyses` — id, user_id, resource_group, resources_scanned (int), issues_found (int), estimated_savings (text), analysis_result (jsonb), status, created_at
- After AI analysis completes, store the full result in the `analyses` table.
- Add a `GET /api/history` endpoint that returns past analyses for the authenticated user.

### WebSocket Progress

- Add a WebSocket endpoint `ws://localhost:8000/ws/progress/{analysis_id}`.
- During the `POST /api/analyze` flow, push progress messages through the WebSocket at each stage:
  - `"Fetching resource groups..."`
  - `"Scanning resources in <rg>..."`
  - `"Analyzing costs with AI..."`
  - `"Storing results..."`
  - `"Analysis complete"`
- The frontend will connect to this WebSocket to show live progress.

### Update .env.example

Add `DATABASE_URL` to `.env.example`.

## Project structure update

```
backend/
├── main.py          (updated — history endpoint, WebSocket, DB init)
├── aws_scanner.py   (no change)
├── ai_analyzer.py   (no change)
├── db.py            (new — DB connection, table creation, queries)
├── requirements.txt (updated — add asyncpg/psycopg2, websockets)
├── .env.example     (updated — add DATABASE_URL)
```

Refer to `Architecture.MD` and `RequestFlow.MD`. This covers steps ④ and ⑥ of the request flow.
