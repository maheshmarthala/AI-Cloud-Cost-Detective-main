# ==============================================================================
# Teardown Bedrock Cost Copilot Resources
# ==============================================================================

param (
    [string]$Region = "ap-southeast-2"
)

$fnName = "bedrock-cost-copilot"
$roleName = "bedrock-cost-copilot-role"
$ruleName = "weekly-cost-copilot-trigger"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Tearing Down Bedrock Cost Copilot Resources             " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Delete EventBridge Rule
Write-Host "Removing EventBridge rule and targets..." -ForegroundColor Yellow
aws events remove-targets --rule $ruleName --ids "1" --region $Region 2>$null | Out-Null
aws events delete-rule --name $ruleName --region $Region 2>$null | Out-Null

# 2. Delete Lambda Function
Write-Host "Deleting Lambda function: $fnName..." -ForegroundColor Yellow
aws lambda delete-function --function-name $fnName --region $Region 2>$null | Out-Null

# 3. Delete IAM Role
Write-Host "Deleting IAM role: $roleName..." -ForegroundColor Yellow
aws iam delete-role-policy --role-name $roleName --policy-name "CostCopilotPermissions" 2>$null | Out-Null
aws iam detach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" 2>$null | Out-Null
aws iam delete-role --role-name $roleName 2>$null | Out-Null

# 4. Delete SNS Topic
$accountId = (aws sts get-caller-identity --query "Account" --output text 2>$null)
if ($accountId) {
    Write-Host "Deleting SNS Topic: cost-copilot-alerts..." -ForegroundColor Yellow
    aws sns delete-topic --topic-arn "arn:aws:sns:$($Region):$($accountId):cost-copilot-alerts" --region $Region 2>$null | Out-Null
}

$zip = Join-Path $PSScriptRoot "copilot.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }

Write-Host "`nCleanup Complete! All resources removed." -ForegroundColor Green
