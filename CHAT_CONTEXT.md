# AI Cloud Cost Detective — Project & Chat Context

> **Context Document for AI Token Optimization**  
> This file contains the complete analysis and context of the `AI-Cloud-Cost-Detective-main` project generated from an in-depth codebase inspection. It can be directly loaded into any LLM or AI session to understand the codebase without re-indexing all source files.

---

## 1. Project Overview & Problem Solved

* **Project Name:** AI Cloud Cost Detective (AWS)
* **Problem Solved:** Managing cloud costs in AWS is challenging because unattached storage, idle instances, unmonitored load balancers, and unmanaged S3 buckets silently accumulate charges. Finding these issues normally requires manually clicking through multiple AWS console pages or parsing complex billing data.
* **Core Solution:** A web-based inspection tool where users sign in, pick AWS regions and services, and trigger an automated audit:
  1. The backend runs read-only AWS CLI commands to discover active resources and configurations.
  2. Selected configuration metadata is passed to **OpenAI GPT-4o** using structured outputs (`CostReport` Pydantic model).
  3. The app produces an actionable report with severity levels, explanations, potential monthly savings, and safe AWS CLI verification commands.
* **Safety & Security Principles:**
  * All scans are **strictly read-only** (`describe-`, `list-`, `get-` calls).
  * Fix commands are recommendations for human review and are **never executed automatically**.
  * Contains a fully functional **Demo Mode** (`DEMO_MODE=true`) that uses synthetic data and requires zero AWS credentials or OpenAI API keys.

---

## 2. Architecture & System Diagram

```mermaid
flowchart TD
    subgraph Client["Frontend (React 19 + TypeScript + Vite)"]
        UI["SPA Dashboard / History / Report"]
        AuthStorage["localStorage (Bearer JWT)"]
    end

    subgraph Server["Backend (FastAPI + Python 3.10+)"]
        API["FastAPI REST Endpoints (/api)"]
        WS["WebSocket Server (/ws/progress/{id})"]
        AuthModule["Auth & Security (bcrypt + PyJWT)"]
        TaskManager["In-Memory Task Admission (Max 4 concurrent)"]
        Scanner["AWS Scanner (aws_scanner.py)"]
        AI["AI Analyzer (ai_analyzer.py)"]
    end

    subgraph Data["Database Layer"]
        DB[("SQLite (local) / PostgreSQL (RDS)")]
    end

    subgraph External["External Services (Live Mode)"]
        AWSCLI["AWS CLI v2 (Subprocess Execution)"]
        AWSServices["AWS (STS, EC2, EBS, RDS, ELBv2, S3)"]
        OpenAI["OpenAI API (GPT-4o Structured Outputs)"]
    end

    UI -->|REST API with Bearer Token| API
    UI <-->|WebSocket Progress Streaming| WS
    API --> AuthModule
    API --> TaskManager
    TaskManager --> Scanner
    Scanner -->|DEMO_MODE=false: exec 'aws'| AWSCLI
    AWSCLI --> AWSServices
    Scanner -->|Discovered Metadata| AI
    AI -->|DEMO_MODE=false: HTTPS| OpenAI
    API <-->|SQLAlchemy Async / aiosqlite / asyncpg| DB
```

---

## 3. Technology Stack & Dependencies

### Backend (`backend/`)
* **Python Runtime:** Python 3.10+ (CI uses Python 3.12).
* **Web Framework:** FastAPI `0.135.2`, Uvicorn `0.41.0`.
* **Authentication:** PyJWT `2.12.1`, bcrypt `5.0.0` (salted password hashes, 8-hour token expiry).
* **Database & ORM:** SQLAlchemy `2.0.48` (asyncio), aiosqlite `0.22.1` (local SQLite), asyncpg `0.31.0` (production PostgreSQL with required TLS).
* **AI Integration:** Official `google-genai` Python SDK natively for Google Gemini (`gemini-2.5-flash`), with fallback to `openai` SDK (`gpt-4o`) if using OpenAI. Both use native Pydantic schema validation for structured outputs.
* **AWS Integration:** AWS CLI v2 executed via `asyncio.create_subprocess_exec` (not Boto3).
* **Validation:** Pydantic v2, email-validator `2.3.0`.
* **Testing:** Pytest `9.0.2`, HTTPX `0.28.1`, Starlette TestClient.

### Frontend (`frontend/`)
* **Runtime & Bundler:** Node.js 22.12+ (24 recommended), Vite `7.3.1`.
* **UI Framework & Routing:** React `19.2.0`, React Router v7 (`react-router-dom` `7.13.0`).
* **Language:** TypeScript `~5.9.3`.
* **Styling:** Tailwind CSS `3.4.19`, PostCSS `8.5.6`, Autoprefixer.
* **E2E Testing:** Playwright `@playwright/test` `1.64.1`.

---

## 4. Folder Structure & Key Files

```
AI-Cloud-Cost-Detective-main/
├── README.md                      # Comprehensive setup, architecture notes, and limitations
├── Architecture.md                # System diagram and component descriptions
├── RequestFlow.md                 # Analysis request lifecycle
├── .github/workflows/ci.yml       # GitHub Actions running pytest and npm build
├── docs/
│   ├── iam-readonly-policy.json   # Minimal read-only IAM policy for AWS CLI
│   └── specifications/            # Historical prompt specs (superseded Resource Group design)
├── backend/
│   ├── main.py                    # FastAPI entrypoint, REST & WebSocket routes, task queue
│   ├── config.py                  # Environment config parsing (DEMO_MODE, JWT_SECRET, etc.)
│   ├── db.py                      # SQLAlchemy models (User, Analysis), DB setup, migration
│   ├── aws_scanner.py             # Subprocess calls to AWS CLI; mock demo fixtures
│   ├── ai_analyzer.py             # OpenAI GPT-4o adapter, CostReport & Issue schemas
│   ├── detective.db               # Local SQLite database
│   ├── requirements.txt           # Python dependencies
│   ├── requirements-dev.txt       # Dev/test requirements (pytest, httpx)
│   ├── requirements.lock          # Locked pip dependency versions
│   ├── .env.example               # Template environment configuration
│   └── tests/
│       ├── conftest.py            # Temporary SQLite fixture & mock test env
│       └── test_app.py            # Pytest test suite (auth, isolation, scans, AI parser)
└── frontend/
    ├── package.json               # Node dependencies and scripts
    ├── vite.config.ts             # Dev proxy for /api and /ws -> http://127.0.0.1:8000
    ├── playwright.config.ts       # E2E test configuration
    └── src/
        ├── main.tsx               # Root DOM mounting
        ├── App.tsx                # App shell, banner, routing, auth protection
        ├── api.ts                 # Fetch wrapper with Bearer token injection & 401 handling
        ├── types.ts               # TypeScript interfaces (Analysis, Issue, ScanConfig)
        ├── components/
        │   ├── Navbar.tsx         # Header navigation and Sign Out
        │   └── ProgressTracker.tsx# Stepper showing live scan progress
        └── pages/
            ├── Login.tsx          # Login & reusable AuthForm
            ├── Signup.tsx         # User registration
            ├── Dashboard.tsx      # Main scan configuration & WebSocket progress tracker
            ├── History.tsx        # Past 100 investigations list
            └── Report.tsx         # Detailed findings view with copyable CLI commands
```

---

## 5. Execution Flow & Lifecycle

1. **Server Startup:**
   * Backend starts via `uvicorn main:app --host 0.0.0.0 --port 8000`.
   * In `lifespan`: `initialize_database()` runs table creation, checks for the `scan_config` column, and marks any previously running/queued analyses as `failed` (single-worker resilience).
2. **Frontend Mount:**
   * Browser loads single-page application at port 5173.
   * `App.tsx` calls `GET /api/health` to detect backend availability and whether it is in Demo Mode.
3. **User Authentication:**
   * User registers or signs in (`POST /api/auth/signup` or `/login`).
   * Passwords hashed via bcrypt. PyJWT generates an 8-hour token stored in browser `localStorage`.
4. **Scan Options Discovery:**
   * Dashboard calls `GET /api/scan-options`.
   * In live mode, backend executes `aws sts get-caller-identity` and `aws ec2 describe-regions` to populate valid options.
   * In demo mode, returns demo account `000000000000` and regions `us-east-1`, `ap-south-1`.
5. **Trigger Analysis:**
   * User selects 1–5 regions, services (`ec2`, `ebs`, `rds`, `s3`, `elbv2`), and optional tag key-values.
   * Frontend posts to `POST /api/analyze`.
   * The server checks admission concurrency (max 4 concurrent tasks, returns 429 if busy).
   * Generates a UUID `identifier`, records an `Analysis` row with `status='queued'`, launches a background `asyncio.create_task(run_analysis(...))`, and returns `HTTP 202 Accepted`.
6. **Real-time Progress Streaming:**
   * Dashboard connects to `ws://localhost:5173/ws/progress/{analysis_id}`.
   * First message payload sends `{ token: "<JWT>" }`.
   * Server validates user ownership and streams progress updates (`Verifying AWS account...`, `Scanning...`, `Analyzing with AI...`).
   * Dashboard also polls `GET /api/analyses/{id}` every 2 seconds as a fallback.
7. **Resource Inventory & AI Analysis:**
   * Background task runs `aws_scanner.scan_account()`. Rejects request if account ID does not match active STS credentials.
   * Runs read-only CLI calls with semaphore-limited parallelism (concurrency 4).
   * Sanitizes attributes (removes endpoints, sensitive config, payloads) and applies exact tag matching.
   * In `ai_analyzer.analyze()`, sends sanitized metadata to OpenAI GPT-4o with instructions forbidding speculative utilization assumptions and demanding copyable read-only verification commands.
   * In Demo Mode, creates synthetic unattached EBS volume findings.
8. **Completion & Presentation:**
   * Result saved with `status='completed'`.
   * Terminal WebSocket message delivered, socket closes.
   * Frontend redirects to `/reports/{analysis_id}` displaying summary cards, limitations, and copyable remediation commands.

---

## 6. Business Logic Example: Orphaned EBS Volume

* **Detection:** Scanner executes `aws ec2 describe-volumes --region us-east-1` and finds a volume with `State: "available"` and `Attachments: []`.
* **AI Analysis:** Identifies that this unattached disk is accumulating storage fees without any attached compute instance.
* **Generated Finding:**
  * **Resource:** `vol-0123456789abcdef0`
  * **Issue Type:** `unused`
  * **Severity:** `medium`
  * **Explanation:** Volume is unattached. Verify ownership and take a snapshot before deletion.
  * **Estimated Savings:** `~$8.00/month` (conditional estimate).
  * **Suggested Fix Command:** `aws ec2 describe-volumes --volume-ids vol-0123456789abcdef0 --region us-east-1` (non-destructive inspection command).

---

## 7. Configuration & Environment Variables

Variable names only (no secrets):
* `DEMO_MODE`: `true` or `false`.
* `JWT_SECRET`: Random string (minimum 32 characters; enforced on startup).
* `DATABASE_URL`: `sqlite+aiosqlite:///./detective.db` or `postgresql://user:pass@host:5432/detective?sslmode=require`.
* `AWS_REGION`: Default AWS fallback region (e.g., `us-east-1`).
* `OPENAI_API_KEY`: OpenAI API key (required when `DEMO_MODE=false`).
* `OPENAI_MODEL`: Model name (defaults to `gpt-4o`).
* `CORS_ORIGINS`: Comma-separated frontend origins (e.g., `http://localhost:5173,http://127.0.0.1:5173`).

---

## 8. Quick Commands for Installation, Running, & Testing

```bash
# 1. Backend Setup
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\Activate.ps1
pip install -r backend/requirements.lock
cp backend/.env.example backend/.env
# Set DEMO_MODE=true and JWT_SECRET (>= 32 chars) in backend/.env

# Run backend
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000

# 2. Frontend Setup (in separate terminal)
cd frontend
npm ci
npm run dev

# 3. Tests
pytest backend/tests -q
cd frontend && npm run build
npm run test:e2e
```

---

## 9. Implementation Status Summary

* **Fully Implemented:** User auth (JWT/bcrypt), read-only AWS scanning (EC2, EBS, RDS, ELBv2, S3), OpenAI GPT-4o structured output, WebSocket progress with event replay, SQLite & PostgreSQL TLS support, React 19 UI, unit/e2e test suites.
* **Mocked / Demo Mode:** Synthetic fixtures for demo account `000000000000`, sample volumes, and mock $8/month savings.
* **Deliberately Not Implemented / Non-Goals:**
  * No live billing ingestion (no AWS Cost Explorer or Pricing API).
  * No utilization metrics (no CloudWatch CPU/RAM or Compute Optimizer).
  * No automated remediation (all fix commands are non-destructive suggestions).
  * Single-worker backend (task set and progress dictionaries are in-memory).

---

## 10. Bugs, Security Issues, & Mismatches

1. **Exposed Key Format in `.env.example`:** `backend/.env.example` line 6 contains an OpenAI key string format and pre-filled JWT secret. This can trigger automated secret scanners.
2. **Tracked Database Binary:** `backend/detective.db` (24 KB) exists on disk despite `.gitignore` specifying `*.db`.
3. **Token Storage:** Tokens are stored in browser `localStorage`, making them vulnerable to XSS if an injection vulnerability exists.
4. **Historical Spec Files:** `docs/specifications/` references an older AWS Resource Groups approach (`/api/resource-groups`), which was replaced by direct region discovery (`/api/scan-options`).
5. **Duplicate Gitignore:** `gitignore.txt` in the root is an accidental duplicate of `.gitignore`.

---

## 11. Recommended Reading Order for Beginners

1. `README.md`
2. `Architecture.md` & `RequestFlow.md`
3. `backend/config.py` & `backend/db.py`
4. `backend/main.py`
5. `backend/aws_scanner.py`
6. `backend/ai_analyzer.py`
7. `frontend/src/types.ts` & `frontend/src/api.ts`
8. `frontend/src/App.tsx` & `frontend/src/pages/Dashboard.tsx`
9. `frontend/src/pages/Report.tsx` & `frontend/src/pages/History.tsx`
10. `backend/tests/test_app.py` & `frontend/tests/flow.spec.ts`
