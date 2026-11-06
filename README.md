# AI Cloud Cost Detective (AWS)

A React + FastAPI application for investigating AWS resource costs. Sign up, confirm the connected AWS account and select regions and services, follow live progress, and review AI recommendations and saved reports. Scanning is read-only; suggested fix commands are never executed.

## Stack and layout

- `backend/`: Python 3.10+, FastAPI, bcrypt/PyJWT, async SQLAlchemy, AWS CLI subprocess scanning, OpenAI structured responses, authenticated WebSockets.
- `frontend/`: Node.js 22.12+ (24 recommended), Vite, React, TypeScript, Tailwind CSS.
- PostgreSQL/RDS for live use; SQLite is supported for local development.
- `docs/specifications/`: original uploaded implementation specifications.
- `Architecture.md` and `RequestFlow.md`: current workflow. The uploaded specifications and PNG are historical references; their Resource Group design is superseded.

## Quick start: local demo

The demo is explicit and uses synthetic resources and analysis. It makes no AWS or OpenAI calls. No cloud credentials are required.

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
cp backend/.env.example backend/.env
```

In `backend/.env`, set `DEMO_MODE=true` and set `JWT_SECRET` to a generated random value of at least 32 characters. Generate one locally with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Start the backend in one terminal:

```bash
cd backend
../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Start the frontend in another:

```bash
cd frontend
npm ci
npm run dev
```

Open the Vite address shown in your terminal (normally port 5173). Create an account with a password of 12–72 characters (at most 72 UTF-8 bytes), confirm demo account `000000000000`, choose a region and services, and run an analysis. Optional tags match exactly (for example, `Environment=demo`). The demo banner and report identify synthetic data. History persists in `backend/detective.db`.

Vite proxies `/api` and `/ws` to the backend, so the browser uses the same origin. Backend API documentation is at `/docs` on port 8000. For a deployed frontend, configure the reverse proxy to route `/api` and WebSocket `/ws` to FastAPI, serve the built SPA with history fallback, and use HTTPS.

## Live AWS, OpenAI, and RDS setup

1. Install **AWS CLI v2** using the [official installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). Configure a read-only role or `aws sso login`. Validate with `aws sts get-caller-identity`. Prefer short-lived role credentials; never commit keys.
2. Set `AWS_REGION` to an enabled default region and set `DEMO_MODE=false`. The dashboard discovers enabled regions and lets you select up to five per scan. No Resource Group is needed.
3. Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` (default `gpt-4o`). Resource ARNs, names, tags, and selected configuration details are sent to OpenAI; review your organization's data policy before live scanning.
4. Set `DATABASE_URL=postgresql://user:password@host:5432/detective?sslmode=require`. URL-encode special characters in credentials. Create the database first; tables are created on startup. Allow port 5432 only from the application network. Connections verify TLS certificates and hostnames even for `sslmode=require`; install the official RDS CA into the runtime trust store if required. Never disable verification.
5. Set a strong private `JWT_SECRET`. Tokens expire after eight hours. Configure `CORS_ORIGINS` with comma-separated exact frontend origins.

## AWS access and scan scope

The account is discovered using `sts get-caller-identity`; users do not enter keys in the browser. The backend uses its AWS CLI credential chain: an EC2 instance role, AWS SSO profile (`AWS_PROFILE`), or securely configured temporary credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN`). Do not put credentials in GitHub or chat. AdministratorAccess is not required.

The dashboard displays the connected account read-only. To switch accounts, assume the intended role or change the backend profile, restart the backend if its environment changed, and refresh account details. Submitting a different account ID never assumes a role: the job fails if it does not match STS. All authenticated application users can scan the connected account within the backend role's permissions; this is not per-user AWS authorization.

A reference read-only policy is in [`docs/iam-readonly-policy.json`](docs/iam-readonly-policy.json). Scope bucket and tag-read permissions to approved resources where possible. The scanner uses:

- `ec2:DescribeRegions`, `ec2:DescribeInstances`, `ec2:DescribeVolumes`
- `rds:DescribeDBInstances`, `rds:ListTagsForResource`
- `elasticloadbalancing:DescribeLoadBalancers`, `elasticloadbalancing:DescribeTags`
- `s3:ListAllMyBuckets`, `s3:GetBucketLocation`, `s3:GetBucketTagging`, `s3:GetLifecycleConfiguration`

STS GetCallerIdentity normally needs no explicit IAM allow. If region discovery is denied, the UI offers only `AWS_REGION` with a warning. Selected service inventory calls paginate automatically through AWS CLI. EC2, EBS, RDS, and ALB/NLB are enumerated directly per selected region. S3 lists account-owned general-purpose buckets once and resolves their locations before including buckets in selected regions; it reads tags and lifecycle configuration without reading object content. S3 directory buckets, classic ELBs, and RDS cluster-level analysis are not supported.

Tag filters are optional, exact, case-sensitive AND matches. The UI supports one key/value pair; the API supports up to ten. Untagged resources are included when no filter is supplied. Missing tags due to permissions cannot be confirmed as matching; those resources may be excluded by a tag filter and the report warns about missing evidence.

Partial discovery failures and inaccessible details appear in report limitations. If every selected service inventory call fails, the job fails instead of claiming that no resources exist. Scanning an entire large account may exceed the model context limit; narrow the service/region/tag scope if analysis fails. Network access is needed for regional STS, EC2, RDS, ELB, and S3 APIs, `api.openai.com`, and the database hostname.

**This is configuration review, not a billing estimator.** EC2 and RDS sizing cannot be judged without utilization. S3 lifecycle absence alone does not prove waste. S3 bytes by storage class, requests, transfer, billing, CloudWatch metrics, Compute Optimizer, Cost Optimization Hub, and live pricing are not collected. Connecting credentials does not enable these unimplemented integrations. AI-generated savings are conditional, not verified billing reductions.

## API

| Endpoint | Behavior |
|---|---|
| `POST /api/auth/signup` | Email/password → bearer token |
| `POST /api/auth/login` | Email/password → bearer token |
| `GET /api/health` | Database readiness and demo/live mode |
| `GET /api/scan-options` | Connected account, enabled regions, services, default region, warnings |
| `POST /api/analyze` | Account/regions/services/tag filters → HTTP 202 with `analysis_id` |
| `GET /api/analyses/{id}` | Owner-only status and full report |
| `GET /api/history` | Latest 100 reports for the current user |
| `/ws/progress/{id}` | First JSON frame: `{ "token": "<JWT>" }`; owner-only progress replay |

Example authenticated analysis request:

```json
{
  "account_id": "123456789012",
  "regions": ["ap-south-1", "us-east-1"],
  "services": ["ec2", "ebs", "rds", "s3"],
  "tag_filters": {"Environment": "Production"}
}
```

Use the actual account ID returned by `/api/scan-options`. Omit `tag_filters` or use `{}` for all matching resources. Supported service identifiers are `ec2`, `ebs`, `rds`, `s3`, and `elbv2`.

Protected HTTP requests require `Authorization: Bearer <token>`. WebSocket tokens are sent in the first frame, never in URLs. Progress is replayed so fast jobs do not lose updates. The UI also polls status if a socket cannot connect. Failures are saved and displayed. Password hashes and tokens never appear in report responses.

## Validation

```bash
.venv/bin/pytest backend/tests -q
cd frontend
npm run build
# With the backend in demo mode on 8000 and Vite on 5173:
npm run test:e2e
```

The backend suite exercises signup/login, protected routes, user isolation for HTTP and WebSockets, full demo analysis, persisted failures, input validation, AWS enrichment, and the OpenAI structured response adapter. Browser tests exercise signup → resource selection → progress → report → history → sign out/login. Live cloud integration requires real service access and is not covered by demo tests.

## Deployment limitations

This is an initial development implementation. Run **one backend worker**: jobs and progress replay use in-process tasks and a bounded cache, with results persisted in the database. Interrupted jobs are marked failed on startup. Multiple workers require a durable queue and shared progress broker first. The process admits at most four concurrent analyses; jobs continue if a browser disconnects.

Before public deployment, add rate limits on authentication and analysis, stronger session controls, monitoring, database migrations/backups, and production secret management. The requested localStorage bearer-token approach is implemented; protect the frontend against XSS and use HTTPS. Inventory does not include utilization metrics, billing data, or a live pricing feed, so AI suggestions and savings estimates require independent verification. No AWS mutation endpoint exists.

## Upgrade from Resource Group scanning

The old `/api/resource-groups` endpoint and `{ "resource_group": ... }` requests are removed. Update API clients to `/api/scan-options` and the request above. History/report responses expose `scope` and nullable `scan_config`, replacing the old `resource_group` field.

At startup an additive migration creates a nullable `scan_config` column in existing SQLite/PostgreSQL databases. The existing physical `resource_group` column is retained internally as the scope label, preserving historical records. Old reports display their original labels and have `scan_config=null`; their results are not rewritten or re-analyzed. Back up the database before upgrading and allow the application database user to add the column. Run a single backend worker during startup/migration.
