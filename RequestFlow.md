# Request Flow

1. Sign up or log in; the backend issues an expiring JWT.
2. `GET /api/scan-options` identifies the backend-authenticated AWS account and available regions/services.
3. Select regions, services, and optional exact-match tags. No Resource Group is required.
4. `POST /api/analyze` accepts the scope and returns an analysis ID. The persisted job verifies that STS identity matches the selected account.
5. AWS CLI directly enumerates selected services and collects configuration and tags. Inventory calls are read-only and paginate automatically.
6. Authenticated WebSocket messages replay progress; REST polling provides a fallback.
7. OpenAI returns structured configuration findings; discovery warnings and missing billing/utilization limitations are added to the report.
8. The backend saves results, scan settings, and status. The user reviews the report and history; commands are suggestions only.

The scanner supports EC2, EBS, RDS instances, ALB/NLB, and general-purpose S3 buckets. A failed service read is not evidence that no resources exist. Empty matches produce no invented issues. Failures are persisted. Historical reports remain readable after the additive database upgrade.
