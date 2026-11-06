import asyncio
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from config import JWT_SECRET
from main import app

SCAN = {'account_id': '000000000000', 'regions': ['us-east-1'], 'services': ['ebs'], 'tag_filters': {}}


@pytest.fixture
def client():
    with TestClient(app) as instance:
        yield instance


def signup(client):
    body = {'email': f'{uuid4().hex}@example.com', 'password': 'correct-horse-battery'}
    response = client.post('/api/auth/signup', json=body)
    assert response.status_code == 201, response.text
    return body, {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_full_flow_and_user_isolation(client):
    body, headers = signup(client)
    assert client.post('/api/auth/signup', json=body).status_code == 409
    assert client.post('/api/auth/login', json={**body, 'password': 'wrong-password'}).status_code == 401
    assert client.post('/api/auth/login', json=body).status_code == 200
    assert client.post('/api/auth/login', json={**body, 'email': 'unknown@example.com'}).status_code == 401
    assert client.get('/api/scan-options', headers=headers).json()['account_id'] == SCAN['account_id']
    response = client.post('/api/analyze', headers=headers, json=SCAN)
    assert response.status_code == 202
    identifier = response.json()['analysis_id']
    with client.websocket_connect(f'/ws/progress/{identifier}') as socket:
        socket.send_json({'token': headers['Authorization'].split()[1]})
        events = []
        while True:
            event = socket.receive_json()
            events.append(event)
            if event['status'] in ('completed', 'failed'):
                break
    assert [event['message'] for event in events] == [
        'Verifying AWS account...', 'Scanning selected regions and services...',
        'Analyzing configuration with AI...', 'Storing results...', 'Analysis complete']
    report = client.get(f'/api/analyses/{identifier}', headers=headers).json()
    assert report['status'] == 'completed'
    assert report['scan_config'] == SCAN
    assert report['scope'] == '000000000000 · us-east-1'
    assert report['resources_scanned'] == 1
    assert report['issues_found'] == 1
    assert report['analysis_result']['issues'][0]['severity'] == 'medium'
    csv_response = client.get(f'/api/analyses/{identifier}/csv', headers=headers)
    assert csv_response.status_code == 200
    assert 'text/csv' in csv_response.headers['content-type']
    assert 'Resource Name' in csv_response.text
    assert any(row['id'] == identifier for row in client.get('/api/history', headers=headers).json())
    _, other_headers = signup(client)
    assert client.get('/api/history', headers=other_headers).json() == []
    assert client.get(f'/api/analyses/{identifier}', headers=other_headers).status_code == 404
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f'/ws/progress/{identifier}') as socket:
            socket.send_json({'token': other_headers['Authorization'].split()[1]})
            socket.receive_json()


def test_auth_and_validation(client):
    for route in ('/api/history', '/api/scan-options', '/api/analyses/missing'):
        assert client.get(route).status_code == 401
    assert client.post('/api/analyze', json=SCAN).status_code == 401
    expired = jwt.encode({'sub': '1', 'iat': 1, 'exp': 2}, JWT_SECRET, algorithm='HS256')
    assert client.get('/api/history', headers={'Authorization': 'Bearer ' + expired}).status_code == 401
    assert client.post('/api/auth/signup', json={'email': 'bad', 'password': 'short'}).status_code == 422
    _, headers = signup(client)
    for bad in ({'resource_group': 'old-group'}, {**SCAN, 'regions': ['--bad; rm /']},
                {**SCAN, 'services': []}, {**SCAN, 'services': ['iam']},
                {**SCAN, 'account_id': 'invalid'}, {**SCAN, 'tag_filters': {'': 'x'}}):
        assert client.post('/api/analyze', headers=headers, json=bad).status_code == 422


def test_failed_job_is_persisted(client):
    _, headers = signup(client)
    identifier = client.post('/api/analyze', headers=headers, json={**SCAN, 'account_id': '111111111111'}).json()['analysis_id']
    with client.websocket_connect(f'/ws/progress/{identifier}') as socket:
        socket.send_json({'token': headers['Authorization'].split()[1]})
        while True:
            event = socket.receive_json()
            if event['status'] == 'failed':
                break
    row = client.get(f'/api/analyses/{identifier}', headers=headers).json()
    assert row['status'] == 'failed'
    assert 'does not match' in row['analysis_result']['error']


def test_direct_regional_discovery_and_tags(monkeypatch):
    import aws_scanner
    calls = []
    monkeypatch.setattr(aws_scanner, 'DEMO_MODE', False)
    async def fake_aws(*args, **kwargs):
        calls.append((args, kwargs.get('region')))
        if args[0] == 'sts':
            return {'Account': SCAN['account_id'], 'Arn': 'arn:aws:iam::000000000000:role/test'}
        if args[:2] == ('ec2', 'describe-instances'):
            return {'Reservations': [{'Instances': [{'InstanceId': 'i-123', 'InstanceType': 'm5.large',
                'Tags': [{'Key': 'Environment', 'Value': 'prod'}, {'Key': 'Name', 'Value': 'app'}], 'UserData': 'private'}]}]}
        if args[:2] == ('ec2', 'describe-volumes'):
            return {'Volumes': [{'VolumeId': 'vol-123', 'Size': 100, 'State': 'available'}]}
        if args[:2] == ('rds', 'describe-db-instances'):
            return {'DBInstances': [{'DBInstanceArn': 'arn:aws:rds:us-east-1:000000000000:db:app',
                'DBInstanceIdentifier': 'app-db', 'DBInstanceClass': 'db.t3.small', 'TagList': []}]}
        if args[:2] == ('elbv2', 'describe-load-balancers'):
            return {'LoadBalancers': [{'LoadBalancerArn': 'arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/test/123',
                'LoadBalancerName': 'test', 'Type': 'application'}]}
        if args[:2] == ('elbv2', 'describe-tags'):
            return {'TagDescriptions': [{'Tags': []}]}
        raise AssertionError(args)
    monkeypatch.setattr(aws_scanner, 'aws', fake_aws)
    result = asyncio.run(aws_scanner.scan_account(SCAN['account_id'], ['us-east-1', 'ap-south-1'], ['ec2', 'ebs', 'rds', 'elbv2'], {}))
    assert len(result['resources']) == 8
    assert {r['region'] for r in result['resources']} == {'us-east-1', 'ap-south-1'}
    assert result['resources'][0]['name'] == 'app'
    assert 'UserData' not in result['resources'][0]['details']
    assert all('resource-groups' not in args for args, _ in calls)
    filtered = asyncio.run(aws_scanner.scan_account(SCAN['account_id'], ['us-east-1'], ['ec2', 'ebs'], {'Environment': 'prod'}))
    assert [r['name'] for r in filtered['resources']] == ['app']


def test_missing_cli_and_timeout(monkeypatch):
    import aws_scanner
    async def missing(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', missing)
    with pytest.raises(aws_scanner.ScanError, match='not installed'):
        asyncio.run(aws_scanner.aws('sts', 'get-caller-identity'))


def test_ai_uses_structured_live_response(monkeypatch):
    import ai_analyzer
    from types import SimpleNamespace
    monkeypatch.setattr(ai_analyzer, 'DEMO_MODE', False)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-not-a-real-key')
    async def parse(**kwargs):
        assert kwargs['response_format'] is ai_analyzer.CostReport
        assert 'untrusted data' in kwargs['messages'][0]['content']
        report = ai_analyzer.CostReport(summary='Needs metrics', issues=[], estimated_savings='Unknown')
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(refusal=None, parsed=report))])
    class Client:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(parse=parse))
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    monkeypatch.setattr(ai_analyzer, 'AsyncOpenAI', Client)
    result = asyncio.run(ai_analyzer.analyze([{'name': 'app'}]))
    assert result['summary'] == 'Needs metrics'
    assert result['issues'] == []


def test_s3_locations_absent_lifecycle_and_permission_warnings(monkeypatch):
    import aws_scanner
    calls = []
    monkeypatch.setattr(aws_scanner, 'DEMO_MODE', False)
    async def fake(*args, **kwargs):
        calls.append(args)
        if args[0] == 'sts':
            return {'Account': SCAN['account_id'], 'Arn': 'arn:aws:iam::000000000000:role/test'}
        if args[1] == 'list-buckets':
            return {'Buckets': [{'Name': 'east'}, {'Name': 'india'}, {'Name': 'other'}]}
        name = args[args.index('--bucket') + 1]
        if args[1] == 'get-bucket-location':
            return {'LocationConstraint': {'east': None, 'india': 'ap-south-1', 'other': 'eu-west-1'}[name]}
        if args[1] == 'get-bucket-tagging':
            if name == 'india':
                raise aws_scanner.ScanError('Denied', 'AccessDenied')
            return {'TagSet': [{'Key': 'Environment', 'Value': 'prod'}]}
        raise aws_scanner.ScanError('No lifecycle configured', 'NoSuchLifecycleConfiguration')
    monkeypatch.setattr(aws_scanner, 'aws', fake)
    result = asyncio.run(aws_scanner.scan_account(SCAN['account_id'], ['us-east-1', 'ap-south-1'], ['s3'], {}))
    assert [r['name'] for r in result['resources']] == ['east', 'india']
    assert all(r['details']['lifecycle_rules'] == [] for r in result['resources'])
    assert sum(call[1] == 'list-buckets' for call in calls) == 1
    assert any('tags unavailable' in note for note in result['warnings'])
    assert any('cost cannot be calculated' in note for note in result['warnings'])


def test_partial_and_total_discovery_failures(monkeypatch):
    import aws_scanner
    monkeypatch.setattr(aws_scanner, 'DEMO_MODE', False)
    async def fake(*args, **kwargs):
        if args[0] == 'sts':
            return {'Account': SCAN['account_id'], 'Arn': 'arn:aws:iam::000000000000:role/test'}
        if args[1] == 'describe-instances':
            return {'Reservations': []}
        raise aws_scanner.ScanError('Read access denied')
    monkeypatch.setattr(aws_scanner, 'aws', fake)
    result = asyncio.run(aws_scanner.scan_account(SCAN['account_id'], SCAN['regions'], ['ec2', 'rds'], {}))
    assert result['resources'] == []
    assert 'rds' in result['warnings'][0]
    with pytest.raises(aws_scanner.ScanError, match='All selected service scans failed'):
        asyncio.run(aws_scanner.scan_account(SCAN['account_id'], SCAN['regions'], ['rds'], {}))


def test_no_matching_demo_resources_has_no_invented_issues(client):
    _, headers = signup(client)
    identifier = client.post('/api/analyze', headers=headers, json={**SCAN, 'tag_filters': {'Environment': 'absent'}}).json()['analysis_id']
    with client.websocket_connect(f'/ws/progress/{identifier}') as socket:
        socket.send_json({'token': headers['Authorization'].split()[1]})
        while socket.receive_json()['status'] not in ('completed', 'failed'):
            pass
    row = client.get(f'/api/analyses/{identifier}', headers=headers).json()
    assert row['status'] == 'completed'
    assert row['resources_scanned'] == 0
    assert row['issues_found'] == 0
    assert row['analysis_result']['issues'] == []


def test_legacy_database_migration_preserves_reports(monkeypatch, tmp_path):
    import db
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    async def check():
        engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'legacy.db'))
        monkeypatch.setattr(db, 'engine', engine)
        async with engine.begin() as connection:
            await connection.execute(text('''CREATE TABLE analyses (
                id VARCHAR(36) PRIMARY KEY, user_id INTEGER, resource_group VARCHAR(128),
                resources_scanned INTEGER, issues_found INTEGER, estimated_savings TEXT,
                analysis_result JSON, status VARCHAR(20), created_at DATETIME)'''))
            await connection.execute(text('''INSERT INTO analyses VALUES
                ('legacy', 1, 'original-group', 1, 0, 'Unknown', '{}', 'completed', '2026-10-26 00:00:00')'''))
        await db.initialize_database()
        await db.initialize_database()  # Repeat startup must be safe.
        async with async_sessionmaker(engine)() as session:
            result = db.serialize(await session.get(db.Analysis, 'legacy'))
            assert result['scope'] == 'original-group'
            assert result['scan_config'] is None
            assert result['status'] == 'completed'
        await engine.dispose()
    asyncio.run(check())


def test_region_discovery_and_fallback(monkeypatch):
    import aws_scanner
    monkeypatch.setattr(aws_scanner, 'DEMO_MODE', False)
    async def fake(*args, **kwargs):
        if args[0] == 'sts':
            return {'Account': SCAN['account_id'], 'Arn': 'arn:aws:iam::000000000000:role/test'}
        return {'Regions': [
            {'RegionName': 'us-east-1', 'OptInStatus': 'opt-in-not-required'},
            {'RegionName': 'ap-south-1', 'OptInStatus': 'opted-in'},
            {'RegionName': 'af-south-1', 'OptInStatus': 'not-opted-in'}]}
    monkeypatch.setattr(aws_scanner, 'aws', fake)
    result = asyncio.run(aws_scanner.scan_options())
    assert result['regions'] == ['ap-south-1', 'us-east-1']
    async def denied(*args, **kwargs):
        if args[0] == 'sts':
            return await fake(*args, **kwargs)
        raise aws_scanner.ScanError('Denied')
    monkeypatch.setattr(aws_scanner, 'aws', denied)
    result = asyncio.run(aws_scanner.scan_options())
    assert result['regions'] == [aws_scanner.AWS_REGION]
    assert result['warnings']


def test_partial_coverage_warning_is_in_saved_report(client, monkeypatch):
    import aws_scanner
    async def partial(**kwargs):
        return {'resources': [], 'warnings': ['RDS discovery denied; coverage is incomplete.']}
    monkeypatch.setattr(aws_scanner, 'scan_account', partial)
    _, headers = signup(client)
    identifier = client.post('/api/analyze', headers=headers, json=SCAN).json()['analysis_id']
    with client.websocket_connect(f'/ws/progress/{identifier}') as socket:
        socket.send_json({'token': headers['Authorization'].split()[1]})
        while socket.receive_json()['status'] not in ('completed', 'failed'):
            pass
    row = client.get(f'/api/analyses/{identifier}', headers=headers).json()
    assert row['status'] == 'completed'
    assert 'RDS discovery denied; coverage is incomplete.' in row['analysis_result']['limitations']
    assert row['issues_found'] == 0
