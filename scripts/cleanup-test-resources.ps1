# ==============================================================================
# AI Cloud Cost Detective - Test Infrastructure Cleanup
# Deletes resources recorded in test-resources.json
# ==============================================================================

$jsonPath = Join-Path $PSScriptRoot "test-resources.json"
if (-not (Test-Path $jsonPath)) {
    Write-Host "No test-resources.json found in $PSScriptRoot. Nothing to clean up." -ForegroundColor Yellow
    exit 0
}

$resources = Get-Content $jsonPath -Raw | ConvertFrom-Json
$region = if ($resources.Region) { $resources.Region } else { "ap-southeast-2" }

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AI Cloud Cost Detective: Cleaning Up Test Resources     " -ForegroundColor Cyan
Write-Host "  Target Region: $region                                  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Terminate EC2 Instances
if ($resources.EC2Instances -and $resources.EC2Instances.Count -gt 0) {
    Write-Host "`n[1/4] Terminating EC2 Instances: $($resources.EC2Instances -join ', ')..." -ForegroundColor Yellow
    aws ec2 terminate-instances --instance-ids $resources.EC2Instances --region $region | Out-Null
    Write-Host "Waiting for EC2 instances to terminate before deleting EBS volumes..." -ForegroundColor Yellow
    aws ec2 wait instance-terminated --instance-ids $resources.EC2Instances --region $region 2>$null
    Write-Host "EC2 instances terminated." -ForegroundColor Green
}

# 2. Delete Standalone EBS Volumes
if ($resources.EBSVolumes -and $resources.EBSVolumes.Count -gt 0) {
    Write-Host "`n[2/4] Deleting EBS Volumes: $($resources.EBSVolumes -join ', ')..." -ForegroundColor Yellow
    foreach ($vol in $resources.EBSVolumes) {
        aws ec2 delete-volume --volume-id $vol --region $region 2>$null
        Write-Host "Deleted EBS Volume: $vol" -ForegroundColor Green
    }
}

# 3. Delete S3 Buckets
if ($resources.S3Buckets -and $resources.S3Buckets.Count -gt 0) {
    Write-Host "`n[3/4] Deleting S3 Buckets: $($resources.S3Buckets -join ', ')..." -ForegroundColor Yellow
    foreach ($bucket in $resources.S3Buckets) {
        aws s3 rb "s3://$bucket" --force --region $region 2>$null
        Write-Host "Deleted S3 Bucket: $bucket" -ForegroundColor Green
    }
}

# 4. Delete RDS Database
if ($resources.RDSInstance) {
    Write-Host "`n[4/4] Deleting RDS Database: $($resources.RDSInstance)..." -ForegroundColor Yellow
    aws rds delete-db-instance `
        --db-instance-identifier $resources.RDSInstance `
        --skip-final-snapshot `
        --delete-automated-backups `
        --region $region 2>$null | Out-Null
    Write-Host "Triggered deletion for RDS Database: $($resources.RDSInstance)" -ForegroundColor Green
}

Remove-Item -Path $jsonPath -Force -ErrorAction SilentlyContinue
Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  CLEANUP COMPLETE! All test resources deleted.           " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
