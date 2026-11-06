# ==============================================================================
# Deploy Autonomous AI Cost Copilot with Amazon Bedrock
# ==============================================================================

param (
    [string]$NotificationEmail = "",
    [string]$Region = "ap-southeast-2",
    [string]$ModelId = "anthropic.claude-3-haiku-20240307-v1:0"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Deploying Autonomous Cost Copilot (Bedrock + Lambda)    " -ForegroundColor Cyan
Write-Host "  Region: $Region                                         " -ForegroundColor Cyan
Write-Host "  Model:  $ModelId                                        " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check AWS identity
Write-Host "`n[1/6] Verifying AWS Credentials..." -ForegroundColor Yellow
$accountId = (aws sts get-caller-identity --query "Account" --output text 2>&1)
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: AWS CLI is not configured or logged in." -ForegroundColor Red
    exit 1
}
Write-Host "Connected AWS Account: $accountId" -ForegroundColor Green

# 2. Setup Amazon SNS Topic for Email Alerts
$topicArn = ""
if ($NotificationEmail) {
    Write-Host "`n[2/6] Configuring Amazon SNS Alert Topic for: $NotificationEmail..." -ForegroundColor Yellow
    $topicArn = (aws sns create-topic --name "cost-copilot-alerts" --region $Region --query "TopicArn" --output text)
    aws sns subscribe `
        --topic-arn $topicArn `
        --protocol email `
        --notification-endpoint $NotificationEmail `
        --region $Region | Out-Null
    Write-Host "Subscription request sent to $NotificationEmail. (Check your inbox and click 'Confirm Subscription')." -ForegroundColor Cyan
} else {
    Write-Host "`n[2/6] Skipping SNS Email setup (pass -NotificationEmail 'you@example.com' to enable)." -ForegroundColor Yellow
}

# 3. Create IAM Execution Role
Write-Host "`n[3/6] Setting up IAM Role with Bedrock & Scanner Permissions..." -ForegroundColor Yellow
$roleName = "bedrock-cost-copilot-role"
$roleArn = "arn:aws:iam::$($accountId):role/$($roleName)"

$roleCheck = aws iam get-role --role-name $roleName 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating IAM role: $roleName..." -ForegroundColor Yellow
    $trustFile = Join-Path $PSScriptRoot "trust.json"
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' | Set-Content -Path $trustFile -Encoding ascii
    aws iam create-role --role-name $roleName --assume-role-policy-document "file://$trustFile" | Out-Null
    Remove-Item $trustFile -Force -ErrorAction SilentlyContinue
    
    # Attach execution policy
    aws iam attach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" | Out-Null
} else {
    Write-Host "IAM Role '$roleName' exists. Updating policy..." -ForegroundColor Yellow
}

# Attach inline policy via temporary JSON file to avoid PowerShell newline escaping issues
$policyFile = Join-Path $PSScriptRoot "copilot-policy.json"
@'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInvoke",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "*"
    },
    {
      "Sid": "ReadInventory",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeVolumes",
        "ec2:DescribeAvailabilityZones",
        "s3:ListAllMyBuckets",
        "s3:GetBucketLocation",
        "s3:GetBucketLifecycleConfiguration",
        "rds:DescribeDBInstances",
        "sns:Publish"
      ],
      "Resource": "*"
    }
  ]
}
'@ | Set-Content -Path $policyFile -Encoding ascii

aws iam put-role-policy --role-name $roleName --policy-name "CostCopilotPermissions" --policy-document "file://$policyFile" | Out-Null
Remove-Item $policyFile -Force -ErrorAction SilentlyContinue

Write-Host "Waiting 10 seconds for IAM propagation..." -ForegroundColor Yellow
Start-Sleep -Seconds 10
Write-Host "IAM Role ready: $roleName" -ForegroundColor Green

# 4. Package Code
Write-Host "`n[4/6] Packaging copilot.py..." -ForegroundColor Yellow
$codeFile = Join-Path $PSScriptRoot "copilot.py"
$zipFile = Join-Path $PSScriptRoot "copilot.zip"
if (Test-Path $zipFile) { Remove-Item $zipFile -Force }
Compress-Archive -Path $codeFile -DestinationPath $zipFile -Force
Write-Host "Package created: copilot.zip" -ForegroundColor Green

# 5. Create or Update Lambda Function
Write-Host "`n[5/6] Deploying Lambda Function (bedrock-cost-copilot)..." -ForegroundColor Yellow
$fnName = "bedrock-cost-copilot"

# Note: AWS_REGION is a reserved key in AWS Lambda; TARGET_REGION is used instead.
$envVars = if ($topicArn) {
    "Variables={TARGET_REGION=$Region,SNS_TOPIC_ARN=$topicArn,BEDROCK_MODEL_ID=$ModelId}"
} else {
    "Variables={TARGET_REGION=$Region,BEDROCK_MODEL_ID=$ModelId}"
}

$fnCheck = aws lambda get-function --function-name $fnName --region $Region 2>&1
if ($LASTEXITCODE -ne 0) {
    aws lambda create-function `
        --function-name $fnName `
        --runtime python3.12 `
        --role $roleArn `
        --handler copilot.lambda_handler `
        --zip-file "fileb://$zipFile" `
        --timeout 120 `
        --memory-size 256 `
        --environment $envVars `
        --region $Region | Out-Null
    Write-Host "Created new Lambda function: $fnName" -ForegroundColor Green
} else {
    aws lambda update-function-code `
        --function-name $fnName `
        --zip-file "fileb://$zipFile" `
        --region $Region | Out-Null
    
    aws lambda update-function-configuration `
        --function-name $fnName `
        --timeout 120 `
        --memory-size 256 `
        --environment $envVars `
        --region $Region | Out-Null
    Write-Host "Updated existing Lambda function: $fnName" -ForegroundColor Green
}

# 6. EventBridge Weekly Cron Schedule
Write-Host "`n[6/6] Setting up EventBridge Schedule (Every Monday 9:00 AM UTC)..." -ForegroundColor Yellow
$ruleName = "weekly-cost-copilot-trigger"
aws events put-rule `
    --name $ruleName `
    --schedule-expression "cron(0 9 ? * MON *)" `
    --state ENABLED `
    --region $Region | Out-Null

$fnArn = (aws lambda get-function --function-name $fnName --region $Region --query "Configuration.FunctionArn" --output text)

aws lambda add-permission `
    --function-name $fnName `
    --statement-id "EventBridgeInvokePermission" `
    --action "lambda:InvokeFunction" `
    --principal "events.amazonaws.com" `
    --source-arn "arn:aws:events:$($Region):$($accountId):rule/$($ruleName)" `
    --region $Region 2>$null | Out-Null

aws events put-targets `
    --rule $ruleName `
    --targets "Id=1,Arn=$fnArn" `
    --region $Region | Out-Null

Write-Host "Scheduled trigger configured: Every Monday at 9:00 AM UTC" -ForegroundColor Green

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  DEPLOYMENT COMPLETE!                                    " -ForegroundColor Green
Write-Host "  To run an immediate test scan:                          " -ForegroundColor Cyan
Write-Host "  .\test-run.ps1                                          " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
