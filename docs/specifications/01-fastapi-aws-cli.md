# Prompt 1: FastAPI Backend + AWS CLI

Create a Python FastAPI backend in a `backend/` folder for the AI Cloud Cost Detective project.

## What to build

- A FastAPI server with a `POST /api/analyze` endpoint that accepts `{ "resource_group": "<name>" }`.
- A `GET /api/resource-groups` endpoint that returns the list of AWS resource groups.
- Use Python's `subprocess` module to run AWS CLI commands:
  - `aws resource-groups list-groups --output json` to list all resource groups.
  - `aws resource-groups list-group-resources --group <name> --output json` to fetch all resources in the selected group.
  - `aws resourcegroupstaggingapi get-resources --resource-arn-list <arns> --output json` to fetch tags for those resources.
  - For common cost-relevant services, enrich with size/SKU details (e.g. `aws ec2 describe-instances`, `aws ec2 describe-volumes`, `aws rds describe-db-instances`, `aws elbv2 describe-load-balancers`).
- Parse the AWS CLI JSON output and return a structured response with resource type, name, region, size/instance type (SKU equivalent), and tags. Derive type, region, and name from the ARN.
- Add error handling for AWS CLI not installed, credentials not configured / expired (`aws sts get-caller-identity` fails), and invalid resource group.
- Enable CORS for `http://localhost:5173`.
- Include a `requirements.txt` with `fastapi`, `uvicorn`.

## Project structure

```
backend/
├── main.py
├── aws_scanner.py
├── requirements.txt
```

Refer to `Architecture.MD` and `RequestFlow.MD`. This covers step ③ of the request flow.
