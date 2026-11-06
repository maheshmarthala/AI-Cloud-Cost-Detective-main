import os
import json
import boto3
from datetime import datetime, timezone

REGION = os.environ.get('TARGET_REGION') or os.environ.get('AWS_REGION') or 'ap-southeast-2'
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
PRIMARY_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-haiku-20240307-v1:0')

ec2 = boto3.client('ec2', region_name=REGION)
s3 = boto3.client('s3', region_name=REGION)
rds = boto3.client('rds', region_name=REGION)
bedrock = boto3.client('bedrock-runtime', region_name=REGION)
sns = boto3.client('sns', region_name=REGION)


def collect_inventory():
    """Scans for potential cloud cost leaks in a strictly read-only manner."""
    findings = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'region': REGION,
        'stopped_ec2_instances': [],
        'unattached_ebs_volumes': [],
        'legacy_gp2_volumes': [],
        's3_buckets_without_lifecycle': [],
        'idle_rds_instances': []
    }

    # 1. EC2 Instances (Detect stopped/zombie instances with EBS billing)
    try:
        reservations = ec2.describe_instances().get('Reservations', [])
        for res in reservations:
            for inst in res.get('Instances', []):
                state = inst.get('State', {}).get('Name')
                inst_id = inst.get('InstanceId')
                inst_type = inst.get('InstanceType')
                name_tag = next((t['Value'] for t in inst.get('Tags', []) if t['Key'] == 'Name'), inst_id)
                if state == 'stopped':
                    findings['stopped_ec2_instances'].append({
                        'id': inst_id,
                        'name': name_tag,
                        'type': inst_type,
                        'state': 'stopped',
                        'note': 'Stopped compute, but attached root volume still incurs monthly storage charges.'
                    })
    except Exception as e:
        findings['stopped_ec2_instances'].append({'error': str(e)})

    # 2. EBS Volumes (Detect orphan unattached and legacy gp2 volumes)
    try:
        volumes = ec2.describe_volumes().get('Volumes', [])
        for vol in volumes:
            vol_id = vol.get('VolumeId')
            size_gb = vol.get('Size')
            vol_type = vol.get('VolumeType')
            attachments = vol.get('Attachments', [])
            name_tag = next((t['Value'] for t in vol.get('Tags', []) if t['Key'] == 'Name'), vol_id)

            if len(attachments) == 0:
                findings['unattached_ebs_volumes'].append({
                    'id': vol_id,
                    'name': name_tag,
                    'size_gb': size_gb,
                    'type': vol_type,
                    'note': 'Orphan volume in available state with zero instances attached.'
                })
            elif vol_type == 'gp2':
                findings['legacy_gp2_volumes'].append({
                    'id': vol_id,
                    'name': name_tag,
                    'size_gb': size_gb,
                    'note': 'Using legacy gp2 storage. Upgrading to gp3 saves ~20% per GB.'
                })
    except Exception as e:
        findings['unattached_ebs_volumes'].append({'error': str(e)})

    # 3. S3 Buckets (Detect buckets missing lifecycle rules)
    try:
        buckets = s3.list_buckets().get('Buckets', [])
        for b in buckets:
            b_name = b.get('Name')
            try:
                loc = s3.get_bucket_location(Bucket=b_name).get('LocationConstraint') or 'us-east-1'
                if loc != REGION and REGION != 'us-east-1':
                    continue
            except Exception:
                pass

            try:
                s3.get_bucket_lifecycle_configuration(Bucket=b_name)
            except Exception as lc_err:
                if 'NoSuchLifecycleConfiguration' in str(lc_err):
                    findings['s3_buckets_without_lifecycle'].append({
                        'bucket': b_name,
                        'note': 'Missing lifecycle configuration. Objects never expire or transition to lower-cost tiers.'
                    })
    except Exception as e:
        findings['s3_buckets_without_lifecycle'].append({'error': str(e)})

    # 4. RDS Databases
    try:
        dbs = rds.describe_db_instances().get('DBInstances', [])
        for db in dbs:
            findings['idle_rds_instances'].append({
                'identifier': db.get('DBInstanceIdentifier'),
                'class': db.get('DBInstanceClass'),
                'status': db.get('DBInstanceStatus'),
                'storage_type': db.get('StorageType'),
                'allocated_storage': db.get('AllocatedStorage')
            })
    except Exception as e:
        findings['idle_rds_instances'].append({'error': str(e)})

    return findings


def analyze_with_bedrock(findings):
    """Prompts Amazon Bedrock using the modern unified Converse API with benchmark pricing."""
    prompt = f"""You are the Lead Cloud FinOps Architect at our organization.
Analyze the following AWS inventory audit findings and produce an executive cost optimization report:

AUDIT DATA:
{json.dumps(findings, indent=2)}

FINANCIAL BENCHMARK PRICING RULES (Use these to calculate realistic monthly estimates):
- Aurora Serverless / RDS (db.serverless minimum 0.5 ACU baseline): ~$43.80 / month
- Standard RDS micro instances (db.t3.micro): ~$18.00 / month
- Stopped EC2 instances (root volume storage charge): ~$1.50 - $3.00 / month per instance
- Unattached / Orphan EBS Volumes: ~$0.08 - $0.10 per GB / month
- S3 Buckets without Lifecycle: Potential 40%-70% savings by archiving old data to Glacier ($0.023/GB vs $0.004/GB)

STRICT FORMATTING REQUIREMENTS:
- NEVER use placeholders like $[X], [Your Name], [Contact Info], or brackets anywhere.
- Calculate and output concrete estimated monthly dollar figures (e.g., "$43.80/month" or "Est. $40 - $50/month").
- Sign the report as "Autonomous Cloud Cost Copilot (AWS Bedrock)".

Please structure your report as follows:
1. EXECUTIVE SUMMARY: High-level overview of account health, total potential waste detected, and monthly savings potential with a concrete dollar figure.
2. CRITICAL COST LEAKS & RECOMMENDATIONS: Grouped by severity (HIGH, MEDIUM, LOW) with exact resource IDs, calculated monthly costs, and why they waste money.
3. IMMEDIATE ACTION PLAN: Safe, copyable AWS CLI commands for the DevOps team to remediate the identified waste."""

    # Candidate active models in Sydney / Global
    candidates = [
        PRIMARY_MODEL_ID,
        'anthropic.claude-3-haiku-20240307-v1:0',
        'amazon.nova-micro-v1:0',
        'amazon.nova-lite-v1:0',
        'anthropic.claude-3-5-sonnet-20240620-v1:0'
    ]

    last_error = None
    for model_id in dict.fromkeys(candidates):
        if not model_id:
            continue
        try:
            print(f"Calling Bedrock Converse API with model: {model_id}")
            response = bedrock.converse(
                modelId=model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}]
                    }
                ],
                inferenceConfig={
                    "maxTokens": 1200,
                    "temperature": 0.2
                }
            )
            report = response['output']['message']['content'][0]['text']
            print(f"Bedrock analysis succeeded using {model_id}!")
            return f"[Generated by Amazon Bedrock ({model_id})]\n\n" + report
        except Exception as e:
            print(f"Model {model_id} failed: {e}")
            last_error = e

    # Fallback inventory report if models are undergoing maintenance
    return f"""[Bedrock Notice: {last_error}]

AUTONOMOUS CLOUD AUDIT SUMMARY:
- Target Region: {REGION}
- Stopped EC2 Instances (accruing EBS cost): {len(findings['stopped_ec2_instances'])}
- Unattached Orphan EBS Volumes: {len(findings['unattached_ebs_volumes'])}
- Legacy gp2 Volumes: {len(findings['legacy_gp2_volumes'])}
- S3 Buckets Missing Lifecycle: {len(findings['s3_buckets_without_lifecycle'])}
- Active RDS Instances: {len(findings['idle_rds_instances'])}

Detailed Inventory Data:
{json.dumps(findings, indent=2)}
"""


def lambda_handler(event, context):
    print(f"Starting Autonomous Cost Audit in region: {REGION}")
    findings = collect_inventory()
    print("Inventory collection complete. Analyzing with Amazon Bedrock...")

    report_text = analyze_with_bedrock(findings)
    print("Report generated successfully.")

    if SNS_TOPIC_ARN:
        subject = f"AWS Cost Copilot Audit: {REGION} ({datetime.now().strftime('%b %d, %Y')})"
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=subject[:100],
                Message=report_text
            )
            print(f"Notification published to SNS: {SNS_TOPIC_ARN}")
        except Exception as e:
            print(f"Failed to publish SNS: {e}")

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Cost audit completed successfully',
            'report': report_text
        })
    }
