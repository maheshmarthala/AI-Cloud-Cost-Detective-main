# ==============================================================================
# Diagnose and Fix 403 Forbidden for Lambda Function URL
# ==============================================================================

param (
    [string]$Region = "ap-southeast-2"
)

$fnName = "my-serverless-webapp"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Diagnosing Lambda Function URL Authorization            " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Inspect current Function URL config
Write-Host "`n[1/4] Checking Function URL Configuration..." -ForegroundColor Yellow
$configJson = aws lambda get-function-url-config --function-name $fnName --region $Region 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Function URL config missing or error: $configJson" -ForegroundColor Red
    Write-Host "Creating Function URL with AuthType=NONE..." -ForegroundColor Yellow
    aws lambda create-function-url-config --function-name $fnName --auth-type NONE --region $Region
} else {
    Write-Host $configJson -ForegroundColor Gray
    # Force AuthType to NONE
    Write-Host "`nEnsuring AuthType is explicitly set to NONE..." -ForegroundColor Yellow
    aws lambda update-function-url-config --function-name $fnName --auth-type NONE --region $Region
}

# 2. Reset and apply public resource-based policy
Write-Host "`n[2/4] Resetting Resource Policy to allow public access..." -ForegroundColor Yellow

# Remove existing statement if present
aws lambda remove-permission `
    --function-name $fnName `
    --statement-id "FunctionURLAllowPublicAccess" `
    --region $Region 2>$null

# Re-add permission explicitly with output visible (no hiding errors)
$permResult = aws lambda add-permission `
    --function-name $fnName `
    --statement-id "FunctionURLAllowPublicAccess" `
    --action "lambda:InvokeFunctionUrl" `
    --principal "*" `
    --function-url-auth-type NONE `
    --region $Region 2>&1

Write-Host "add-permission output: $permResult" -ForegroundColor Gray

# 3. Get Policy to verify
Write-Host "`n[3/4] Verifying Resource Policy in AWS..." -ForegroundColor Yellow
$policy = aws lambda get-policy --function-name $fnName --region $Region 2>&1
Write-Host $policy -ForegroundColor Gray

# 4. Test URL
Write-Host "`n[4/4] Testing Live URL..." -ForegroundColor Yellow
$url = (aws lambda get-function-url-config --function-name $fnName --region $Region --query "FunctionUrl" --output text).Trim()
Write-Host "Function URL: $url" -ForegroundColor Green

try {
    $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
    Write-Host "`nHTTP Status Code: $($resp.StatusCode)" -ForegroundColor Green
    Write-Host "Response Preview:`n$($resp.Content.Substring(0, [Math]::Min(200, $resp.Content.Length)))..." -ForegroundColor Cyan
    Write-Host "`n==========================================================" -ForegroundColor Cyan
    Write-Host "  SUCCESS! Function URL is now publicly accessible.       " -ForegroundColor Green
    Write-Host "  Open in browser: $url" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan
} catch {
    Write-Host "`nTest Request Failed with error: $_" -ForegroundColor Red
}
