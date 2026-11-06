# ==============================================================================
# Run an Instant Cost Audit using Bedrock & Lambda
# ==============================================================================

param (
    [string]$Region = "ap-southeast-2"
)

$fnName = "bedrock-cost-copilot"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Triggering Bedrock Cost Copilot Scan...                 " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$outFile = Join-Path $PSScriptRoot "response.json"

Write-Host "Invoking Lambda in $Region..." -ForegroundColor Yellow
aws lambda invoke `
    --function-name $fnName `
    --region $Region `
    --log-type Tail `
    $outFile | Out-Null

if (Test-Path $outFile) {
    $raw = Get-Content $outFile -Raw | ConvertFrom-Json
    $body = $raw.body | ConvertFrom-Json

    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host "  AMAZON BEDROCK COST REPORT:                             " -ForegroundColor Green
    Write-Host "==========================================================`n" -ForegroundColor Green

    Write-Host $body.report -ForegroundColor White

    Write-Host "`n==========================================================" -ForegroundColor Cyan
    Write-Host "  Audit finished. Check your email if SNS was configured. " -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan

    Remove-Item $outFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "Failed to receive Lambda response." -ForegroundColor Red
}
