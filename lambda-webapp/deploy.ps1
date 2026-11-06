# ==============================================================================
# Deploy Serverless Web App to AWS Lambda
# ==============================================================================

param (
    [string]$Region = "ap-southeast-2"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Deploying Serverless Web App to AWS Lambda              " -ForegroundColor Cyan
Write-Host "  Target Region: $Region                                  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check AWS identity
Write-Host "`n[1/5] Checking AWS Credentials..." -ForegroundColor Yellow
$caller = aws sts get-caller-identity 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: AWS CLI is not configured or logged in." -ForegroundColor Red
    exit 1
}
$accountId = (aws sts get-caller-identity --query "Account" --output text)
Write-Host "Connected AWS Account: $accountId" -ForegroundColor Green

# 2. Setup IAM Role for Lambda
Write-Host "`n[2/5] Checking IAM Execution Role..." -ForegroundColor Yellow
$roleName = "lambda-webapp-basic-role"
$roleArn = "arn:aws:iam::$accountId`:role/$roleName"

$roleCheck = aws iam get-role --role-name $roleName 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating IAM role: $roleName..." -ForegroundColor Yellow
    $trust = '{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"lambda.amazonaws.com\"},\"Action\":\"sts:AssumeRole\"}]}'
    aws iam create-role --role-name $roleName --assume-role-policy-document $trust | Out-Null
    aws iam attach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" | Out-Null
    Write-Host "Waiting 10 seconds for IAM role to propagate across AWS..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
    Write-Host "IAM Role ready." -ForegroundColor Green
} else {
    Write-Host "IAM Role '$roleName' already exists." -ForegroundColor Green
}

# 3. Package code
Write-Host "`n[3/5] Packaging app.py into function.zip..." -ForegroundColor Yellow
$appPath = Join-Path $PSScriptRoot "app.py"
$zipPath = Join-Path $PSScriptRoot "function.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path $appPath -DestinationPath $zipPath -Force
Write-Host "Package created: function.zip" -ForegroundColor Green

# 4. Create or Update Lambda Function
Write-Host "`n[4/5] Deploying Lambda Function..." -ForegroundColor Yellow
$fnName = "my-serverless-webapp"
$fnCheck = aws lambda get-function --function-name $fnName --region $Region 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating new function: $fnName..." -ForegroundColor Yellow
    aws lambda create-function `
        --function-name $fnName `
        --runtime python3.12 `
        --role $roleArn `
        --handler app.lambda_handler `
        --zip-file "fileb://$zipPath" `
        --region $Region | Out-Null
    Write-Host "Function created." -ForegroundColor Green
} else {
    Write-Host "Updating existing function code..." -ForegroundColor Yellow
    aws lambda update-function-code `
        --function-name $fnName `
        --zip-file "fileb://$zipPath" `
        --region $Region | Out-Null
    Write-Host "Function code updated." -ForegroundColor Green
}

# 5. Enable Public Function URL
Write-Host "`n[5/5] Configuring Public HTTPS Function URL..." -ForegroundColor Yellow
$urlCheck = aws lambda get-function-url-config --function-name $fnName --region $Region 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating Function URL configuration..." -ForegroundColor Yellow
    aws lambda create-function-url-config `
        --function-name $fnName `
        --auth-type NONE `
        --region $Region | Out-Null
}

# Always ensure public invocation permission is present
Write-Host "Applying public URL permission..." -ForegroundColor Yellow
aws lambda remove-permission `
    --function-name $fnName `
    --statement-id "FunctionURLAllowPublicAccess" `
    --region $Region 2>$null

aws lambda add-permission `
    --function-name $fnName `
    --statement-id "FunctionURLAllowPublicAccess" `
    --action "lambda:InvokeFunctionUrl" `
    --principal "*" `
    --function-url-auth-type NONE `
    --region $Region 2>$null | Out-Null


$functionUrl = aws lambda get-function-url-config --function-name $fnName --region $Region --query "FunctionUrl" --output text

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  SUCCESS! Your Serverless Web App is LIVE:              " -ForegroundColor Green
Write-Host "  $functionUrl" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
