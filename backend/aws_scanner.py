"""Direct, read-only inventory of the account authenticated by AWS CLI."""
import asyncio
import json
import re
import subprocess

from config import AWS_REGION, DEMO_MODE

SERVICES = ['ec2', 'ebs', 'rds', 's3', 'elbv2']


class ScanError(Exception):
    def __init__(self, message, code=''):
        super().__init__(message)
        self.code = code


def _run_aws_sync(command):
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60,
            check=False
        )
    except FileNotFoundError as exc:
        raise ScanError('AWS CLI v2 is not installed on the server.') from exc
    except subprocess.TimeoutExpired as exc:
        raise ScanError('AWS request timed out. Check region and connectivity.') from exc


async def _run_aws_in_thread(command):
    result = await asyncio.to_thread(_run_aws_sync, command)
    if result.returncode:
        stderr = result.stderr
        match = re.search(r'An error occurred \(([^)]+)\)', stderr)
        code = match[1] if match else ''
        message = 'AWS request failed. Check read permissions, region, and connectivity.'
        if any(word in stderr for word in ('ExpiredToken', 'Unable to locate credentials', 'InvalidClientTokenId')):
            message = 'AWS credentials are missing or expired. Configure AWS CLI authentication.'
        raise ScanError(message, code)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ScanError('AWS CLI returned an invalid response.') from exc


async def aws(*args, region=None):
    command = ['aws', *args, '--region', region or AWS_REGION, '--output', 'json', '--no-cli-pager']
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError as exc:
        raise ScanError('AWS CLI v2 is not installed on the server.') from exc
    except NotImplementedError:
        # On Windows with SelectorEventLoop (e.g. Uvicorn with reload), asyncio subprocesses are not supported.
        return await _run_aws_in_thread(command)

    try:
        output, error = await asyncio.wait_for(process.communicate(), timeout=60)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise ScanError('AWS request timed out. Check region and connectivity.') from exc
    except asyncio.CancelledError:
        process.kill()
        await process.communicate()
        raise
    if process.returncode:
        stderr = error.decode(errors='replace')
        match = re.search(r'An error occurred \(([^)]+)\)', stderr)
        code = match[1] if match else ''
        message = 'AWS request failed. Check read permissions, region, and connectivity.'
        if any(word in stderr for word in ('ExpiredToken', 'Unable to locate credentials', 'InvalidClientTokenId')):
            message = 'AWS credentials are missing or expired. Configure AWS CLI authentication.'
        raise ScanError(message, code)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ScanError('AWS CLI returned an invalid response.') from exc


async def identity():
    if DEMO_MODE:
        return {'Account': '000000000000', 'Arn': 'arn:aws:iam::000000000000:role/demo'}
    return await aws('sts', 'get-caller-identity')


async def scan_options():
    account = await identity()
    warnings = []
    if DEMO_MODE:
        regions = ['us-east-1', 'ap-south-1']
    else:
        try:
            result = await aws('ec2', 'describe-regions', '--all-regions')
            regions = sorted(r['RegionName'] for r in result['Regions']
                             if r.get('OptInStatus') in ('opt-in-not-required', 'opted-in'))
        except ScanError:
            regions = [AWS_REGION]
            warnings.append('Region discovery unavailable. Showing only the configured AWS_REGION.')
    return {'account_id': account['Account'], 'regions': regions, 'services': SERVICES,
            'default_region': AWS_REGION if AWS_REGION in regions else regions[0], 'warnings': warnings}


def tags_dict(tags):
    return {tag['Key']: tag['Value'] for tag in tags}


def resource(arn, kind, name, region, size, tags, details):
    return {'arn': arn, 'type': kind, 'name': tags.get('Name', name), 'region': region,
            'size': size, 'tags': tags, 'details': details, 'warnings': []}


def selected_details(data, keys):
    # Do not send endpoints, connection strings, user data, or unrelated metadata to AI.
    return {key: data[key] for key in keys if key in data}


async def regional_resources(service, region, account):
    resources, warnings = [], []
    partition = account['Arn'].split(':')[1]
    prefix = f'arn:{partition}'
    if service == 'ec2':
        data = await aws('ec2', 'describe-instances', region=region)
        for reservation in data.get('Reservations', []):
            for item in reservation.get('Instances', []):
                identifier = item['InstanceId']
                resources.append(resource(f'{prefix}:ec2:{region}:{account["Account"]}:instance/{identifier}',
                    'AWS::EC2::Instance', identifier, region, item.get('InstanceType'), tags_dict(item.get('Tags', [])),
                    selected_details(item, ('InstanceType', 'State', 'PlatformDetails', 'InstanceLifecycle'))))
    elif service == 'ebs':
        data = await aws('ec2', 'describe-volumes', region=region)
        for item in data.get('Volumes', []):
            identifier = item['VolumeId']
            resources.append(resource(f'{prefix}:ec2:{region}:{account["Account"]}:volume/{identifier}',
                'AWS::EC2::Volume', identifier, region, item.get('Size'), tags_dict(item.get('Tags', [])),
                selected_details(item, ('State', 'Size', 'VolumeType', 'Attachments', 'Iops', 'Throughput'))))
    elif service == 'rds':
        data = await aws('rds', 'describe-db-instances', region=region)
        for item in data.get('DBInstances', []):
            entry = resource(item['DBInstanceArn'], 'AWS::RDS::DBInstance', item['DBInstanceIdentifier'], region,
                item.get('DBInstanceClass'), tags_dict(item.get('TagList', [])),
                selected_details(item, ('DBInstanceClass', 'Engine', 'AllocatedStorage', 'MultiAZ', 'StorageType', 'DBInstanceStatus')))
            if 'TagList' not in item:
                try:
                    tag_data = await aws('rds', 'list-tags-for-resource', '--resource-name', entry['arn'], region=region)
                    entry['tags'] = tags_dict(tag_data.get('TagList', []))
                except ScanError:
                    entry['warnings'].append('RDS tags unavailable; tag-filter matching cannot be confirmed.')
            resources.append(entry)
    elif service == 'elbv2':
        data = await aws('elbv2', 'describe-load-balancers', region=region)
        for item in data.get('LoadBalancers', []):
            entry = resource(item['LoadBalancerArn'], 'AWS::ElasticLoadBalancingV2::LoadBalancer',
                item['LoadBalancerName'], region, item.get('Type'), {},
                selected_details(item, ('Type', 'Scheme', 'State')))
            try:
                tag_data = await aws('elbv2', 'describe-tags', '--resource-arns', entry['arn'], region=region)
                entry['tags'] = tags_dict(tag_data['TagDescriptions'][0].get('Tags', []))
            except ScanError:
                entry['warnings'].append('Load balancer tags unavailable; tag-filter matching cannot be confirmed.')
            resources.append(entry)
    return resources, warnings


async def s3_resources(regions, partition):
    # List account-owned buckets once, then resolve their regions to avoid duplicates.
    data = await aws('s3api', 'list-buckets')
    resources, warnings = [], []
    for bucket in data.get('Buckets', []):
        name = bucket['Name']
        try:
            location = await aws('s3api', 'get-bucket-location', '--bucket', name)
            region = location.get('LocationConstraint') or 'us-east-1'
            if region == 'EU':
                region = 'eu-west-1'
        except ScanError:
            warnings.append(f'S3 bucket {name}: region unavailable; excluded from selected-region inventory.')
            continue
        if region not in regions:
            continue
        entry = resource(f'arn:{partition}:s3:::{name}', 'AWS::S3::Bucket', name, region, None, {}, {})
        for operation, key, absence in (
            ('get-bucket-tagging', 'tags', 'NoSuchTagSet'),
            ('get-bucket-lifecycle-configuration', 'lifecycle_rules', 'NoSuchLifecycleConfiguration')):
            try:
                result = await aws('s3api', operation, '--bucket', name, region=region)
                if key == 'tags':
                    entry['tags'] = tags_dict(result.get('TagSet', []))
                else:
                    entry['details'][key] = result.get('Rules', [])
            except ScanError as exc:
                if exc.code == absence:
                    if key == 'lifecycle_rules':
                        entry['details'][key] = []
                else:
                    entry['warnings'].append(f'S3 {key} unavailable; check bucket read permissions.')
        entry['warnings'].append('S3 size, storage-class usage, requests, and transfer are not collected; cost cannot be calculated.')
        resources.append(entry)
    return resources, warnings


def demo_resources(regions, services):
    region = regions[0]
    fixtures = {
        'ec2': ('AWS::EC2::Instance', 'demo-app', 't3.medium', {'State': {'Name': 'running'}}),
        'ebs': ('AWS::EC2::Volume', 'demo-unattached-volume', 100, {'State': 'available', 'Size': 100, 'VolumeType': 'gp3'}),
        'rds': ('AWS::RDS::DBInstance', 'demo-db', 'db.t3.medium', {'MultiAZ': False}),
        's3': ('AWS::S3::Bucket', 'demo-archive', None, {'lifecycle_rules': []}),
        'elbv2': ('AWS::ElasticLoadBalancingV2::LoadBalancer', 'demo-alb', 'application', {'Scheme': 'internet-facing'}),
    }
    return [resource(f'arn:aws:{service}:{region}:000000000000:demo/{name}', kind, name, region, size,
                     {'Environment': 'demo'}, details)
            for service in services for kind, name, size, details in [fixtures[service]]]


async def scan_account(account_id, regions, services, tag_filters):
    account = await identity()
    if account['Account'] != account_id:
        raise ScanError('Selected account does not match backend AWS credentials. Refresh account details or switch the backend role.')
    warnings = []
    if DEMO_MODE:
        if any(region not in ('us-east-1', 'ap-south-1') for region in regions):
            raise ScanError('Region is not available in demo mode.')
        resources = demo_resources(regions, services)
    else:
        resources, successes = [], 0
        semaphore = asyncio.Semaphore(4)

        async def discover(service, region=None):
            nonlocal successes
            async with semaphore:
                try:
                    batch, notes = await (s3_resources(regions, account['Arn'].split(':')[1]) if service == 's3'
                                          else regional_resources(service, region, account))
                    resources.extend(batch)
                    warnings.extend(notes)
                    successes += 1
                except ScanError as exc:
                    warnings.append(f'{service} in {region or "selected regions"}: {exc}')
        await asyncio.gather(*(discover(service, region) for service in services if service != 's3' for region in regions),
                             *([discover('s3')] if 's3' in services else []))
        if not successes:
            raise ScanError('All selected service scans failed. Check AWS read permissions and enabled regions.')
    for entry in resources:
        warnings.extend(f'{entry["name"]}: {note}' for note in entry['warnings'])
    resources = [entry for entry in resources if all(entry['tags'].get(key) == value for key, value in tag_filters.items())]
    return {'resources': resources, 'warnings': list(dict.fromkeys(warnings))}
