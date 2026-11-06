# AI Cloud Cost Detective — Current Architecture

```mermaid
flowchart LR
    User[Signed-in user] --> UI[React dashboard]
    UI -->|JWT / account + regions + services + optional tags| API[FastAPI]
    API -->|Read-only CLI authentication| STS[AWS STS: connected account]
    API --> Scanner[Direct AWS service discovery]
    Scanner --> EC2[EC2 + EBS]
    Scanner --> RDS[RDS instances]
    Scanner --> ELB[ALB / NLB]
    Scanner --> S3[S3 buckets + tags + lifecycle]
    Scanner -->|Configuration metadata + coverage warnings| AI[OpenAI GPT-4o]
    AI --> API
    API --> DB[(PostgreSQL / local SQLite)]
    API -->|Authenticated WebSocket + REST polling| UI
    DB -->|Saved owner-only reports| API
    UI --> Review[Human verification before changes]
```

No AWS Resource Group is required. AWS identity comes from the backend role/profile; entering an account ID does not grant access or switch accounts. AWS API calls use argument lists without a shell and never mutate resources. Only selected metadata is sent to OpenAI.

Billing, utilization, pricing, realized savings, and automated remediation are not integrated. S3 bucket configuration is collected without reading object contents; storage quantities and request costs remain unknown. Reports identify partial discovery failures and missing evidence. Historical uploaded specifications and `docs/images/cloud-cost-detective-workflow.png` describe the earlier Resource Group design.
