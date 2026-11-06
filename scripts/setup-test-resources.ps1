# ==============================================================================
# AI Cloud Cost Detective - Test Infrastructure Provisioner
# Stay 100% within AWS Free Tier Limits
# ==============================================================================

param (
    [string]$Region = "ap-southeast-2"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AI Cloud Cost Detective: Deploying Test Resources       " -ForegroundColor Cyan
Write-Host "  Target Region: $Region                                  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check AWS Credentials
Write-Host "`n[1/6] Verifying AWS Credentials..." -ForegroundColor Yellow
$caller = aws sts get-caller-identity 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: AWS CLI is not logged in or configured!" -ForegroundColor Red
    Write-Host "Please run 'aws configure' first and enter your credentials." -ForegroundColor Red
    exit 1
}
$accountId = (aws sts get-caller-identity --query "Account" --output text)
Write-Host "Connected to AWS Account: $accountId" -ForegroundColor Green

# 2. Setup Availability Zone and AMI
Write-Host "`n[2/6] Detecting Availability Zone and Free Tier AMI..." -ForegroundColor Yellow
$az = (aws ec2 describe-availability-zones --region $Region --query "AvailabilityZones[0].ZoneName" --output text)
$amiId = (aws ssm get-parameter --name "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" --region $Region --query "Parameter.Value" --output text)
Write-Host "Using AZ: $az" -ForegroundColor Green
Write-Host "Using AMI: $amiId" -ForegroundColor Green

$randomSuffix = Get-Random -Minimum 100000 -Maximum 999999
$trackedResources = @{
    Region = $Region
    S3Buckets = @()
    EC2Instances = @()
    EBSVolumes = @()
    RDSInstance = "cost-detective-db-test"
}

# 3. Create S3 Buckets (Bucket 1: Missing Lifecycle, Bucket 2: With Lifecycle)
Write-Host "`n[3/6] Creating S3 Buckets..." -ForegroundColor Yellow
$bucketNoLc = "cost-detective-no-lc-$randomSuffix"
$bucketWithLc = "cost-detective-with-lc-$randomSuffix"

# Create Bucket 1 (Negative Test: No Lifecycle)
if ($Region -eq "us-east-1") {
    aws s3api create-bucket --bucket $bucketNoLc --region $Region | Out-Null
} else {
    aws s3api create-bucket --bucket $bucketNoLc --region $Region --create-bucket-configuration LocationConstraint=$Region | Out-Null
}
aws s3api put-bucket-tagging --bucket $bucketNoLc --region $Region --tagging 'TagSet=[{Key=Environment,Value=Test}]' | Out-Null
$trackedResources.S3Buckets += $bucketNoLc
Write-Host "Created S3 Bucket (No Lifecycle): $bucketNoLc" -ForegroundColor Green

# Create Bucket 2 (Positive Test: With Lifecycle)
if ($Region -eq "us-east-1") {
    aws s3api create-bucket --bucket $bucketWithLc --region $Region | Out-Null
} else {
    aws s3api create-bucket --bucket $bucketWithLc --region $Region --create-bucket-configuration LocationConstraint=$Region | Out-Null
}
aws s3api put-bucket-tagging --bucket $bucketWithLc --region $Region --tagging 'TagSet=[{Key=Environment,Value=Test}]' | Out-Null

$lcConfig = '{\"Rules\":[{\"ID\":\"ArchiveRule\",\"Status\":\"Enabled\",\"Filter\":{\"Prefix\":\"\"},\"Expiration\":{\"Days\":90}}]}'
aws s3api put-bucket-lifecycle-configuration --bucket $bucketWithLc --region $Region --lifecycle-configuration $lcConfig | Out-Null
$trackedResources.S3Buckets += $bucketWithLc
Write-Host "Created S3 Bucket (With 90-Day Lifecycle): $bucketWithLc" -ForegroundColor Green

# 4. Create Standalone EBS Volumes (Orphan gp3 and Legacy gp2)
Write-Host "`n[4/6] Creating Test EBS Volumes..." -ForegroundColor Yellow

# Orphan Volume (1 GB gp3, unattached)
$orphanVol = (aws ec2 create-volume `
    --availability-zone $az `
    --size 1 `
    --volume-type gp3 `
    --tag-specifications "ResourceType=volume,Tags=[{Key=Name,Value=orphan-test-volume},{Key=Environment,Value=Test}]" `
    --region $Region `
    --query "VolumeId" --output text)
$trackedResources.EBSVolumes += $orphanVol
Write-Host "Created Orphan EBS Volume (gp3 unattached): $orphanVol" -ForegroundColor Green

# Legacy Volume (1 GB gp2, older generation)
$gp2Vol = (aws ec2 create-volume `
    --availability-zone $az `
    --size 1 `
    --volume-type gp2 `
    --tag-specifications "ResourceType=volume,Tags=[{Key=Name,Value=legacy-gp2-volume},{Key=Environment,Value=Test}]" `
    --region $Region `
    --query "VolumeId" --output text)
$trackedResources.EBSVolumes += $gp2Vol
Write-Host "Created Legacy EBS Volume (gp2): $gp2Vol" -ForegroundColor Green

# 5. Launch EC2 Instances (1 Running, 1 Stopped)
Write-Host "`n[5/6] Launching EC2 Instances..." -ForegroundColor Yellow

# Running Instance
$runningInstance = (aws ec2 run-instances `
    --image-id $amiId `
    --instance-type t2.micro `
    --count 1 `
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=test-running-ec2},{Key=Environment,Value=Test}]" "ResourceType=volume,Tags=[{Key=Environment,Value=Test}]" `
    --region $Region `
    --query "Instances[0].InstanceId" --output text) 2>$null

if (-not $runningInstance) {
    # Fallback to t3.micro if t2.micro is unavailable in this region/AZ
    $runningInstance = (aws ec2 run-instances `
        --image-id $amiId `
        --instance-type t3.micro `
        --count 1 `
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=test-running-ec2},{Key=Environment,Value=Test}]" "ResourceType=volume,Tags=[{Key=Environment,Value=Test}]" `
        --region $Region `
        --query "Instances[0].InstanceId" --output text)
}
$trackedResources.EC2Instances += $runningInstance
Write-Host "Launched Running EC2 Instance: $runningInstance" -ForegroundColor Green

# Stopped Instance (Zombie Resource)
$stoppedInstance = (aws ec2 run-instances `
    --image-id $amiId `
    --instance-type t2.micro `
    --count 1 `
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=zombie-stopped-instance},{Key=Environment,Value=Test}]" "ResourceType=volume,Tags=[{Key=Environment,Value=Test}]" `
    --region $Region `
    --query "Instances[0].InstanceId" --output text) 2>$null

if (-not $stoppedInstance) {
    $stoppedInstance = (aws ec2 run-instances `
        --image-id $amiId `
        --instance-type t3.micro `
        --count 1 `
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=zombie-stopped-instance},{Key=Environment,Value=Test}]" "ResourceType=volume,Tags=[{Key=Environment,Value=Test}]" `
        --region $Region `
        --query "Instances[0].InstanceId" --output text)
}
$trackedResources.EC2Instances += $stoppedInstance
Write-Host "Launched EC2 Instance: $stoppedInstance. Stopping it now..." -ForegroundColor Yellow

# Wait a brief moment for the instance to transition then stop it
Start-Sleep -Seconds 5
aws ec2 stop-instances --instance-ids $stoppedInstance --region $Region | Out-Null
Write-Host "Stopped EC2 Instance: $stoppedInstance (Zombie State)" -ForegroundColor Green

# 6. Create Free-Tier RDS PostgreSQL Database
Write-Host "`n[6/6] Creating RDS PostgreSQL Database (Free Tier)..." -ForegroundColor Yellow
$rdsCheck = aws rds describe-db-instances --db-instance-identifier cost-detective-db-test --region $Region 2>&1
if ($LASTEXITCODE -ne 0) {
    aws rds create-db-instance `
        --db-instance-identifier cost-detective-db-test `
        --db-instance-class db.t3.micro `
        --engine postgres `
        --allocated-storage 20 `
        --storage-type gp3 `
        --no-enable-storage-autoscaling `
        --master-username postgres `
        --master-user-password "TestPassword123!" `
        --tags "Key=Environment,Value=Test" `
        --region $Region | Out-Null
    Write-Host "Provisioning RDS DB: cost-detective-db-test (takes ~5-10 mins in background)" -ForegroundColor Green
} else {
    Write-Host "RDS instance 'cost-detective-db-test' already exists." -ForegroundColor Yellow
}

# Save tracking file for 1-click cleanup
$jsonPath = Join-Path $PSScriptRoot "test-resources.json"
$trackedResources | ConvertTo-Json -Depth 5 | Set-Content $jsonPath -Encoding UTF8

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  ALL TEST RESOURCES CREATED SUCCESSFULLY!                " -ForegroundColor Green
Write-Host "  Tracking saved to: $jsonPath" -ForegroundColor Cyan
Write-Host "  Run '.\scripts\cleanup-test-resources.ps1' when finished." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
