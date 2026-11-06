# ==============================================================================
# Teardown Lambda Web App
# ==============================================================================

param (
    [string]$Region = "ap-southeast-2"
)

$fnName = "my-serverless-webapp"
$roleName = "lambda-webapp-basic-role"

Write-Host "Deleting Lambda function: $fnName..." -ForegroundColor Yellow
aws lambda delete-function --function-name $fnName --region $Region 2>$null

Write-Host "Detaching policy and deleting IAM role: $roleName..." -ForegroundColor Yellow
aws iam detach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" 2>$null
aws iam delete-role --role-name $roleName 2>$null

$zipPath = Join-Path $PSScriptRoot "function.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Write-Host "Cleanup complete! Lambda and IAM role removed." -ForegroundColor Green
