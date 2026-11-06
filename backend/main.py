import asyncio
from contextlib import asynccontextmanager
import csv
from datetime import datetime, timedelta, timezone
import io
import logging
import sys
from uuid import uuid4
from typing import Literal

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

import ai_analyzer
import aws_scanner
from config import CORS_ORIGINS, DEMO_MODE, JWT_SECRET
from db import Analysis, Session, User, engine, initialize_database, serialize

logger = logging.getLogger(__name__)
tasks: set[asyncio.Task] = set()
admission_lock = asyncio.Lock()
progress: dict[str, list[dict]] = {}


@asynccontextmanager
async def lifespan(app):
    await initialize_database()
    # This application uses one worker; interrupted jobs are never shown as running forever.
    async with Session() as session:
        await session.execute(update(Analysis).where(Analysis.status.in_(['queued', 'running'])).values(
            status='failed', analysis_result={'error': 'Server restarted. Run this analysis again.'}))
        await session.commit()
    yield
    for task in list(tasks):
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await engine.dispose()


app = FastAPI(title='AI Cloud Cost Detective', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])
security = HTTPBearer(auto_error=False)


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)

    @field_validator('password')
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode()) > 72:
            raise ValueError('Password must be at most 72 UTF-8 bytes.')
        return value


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_id: str = Field(pattern=r'^\d{12}$')
    regions: list[str] = Field(min_length=1, max_length=5)
    services: list[Literal['ec2', 'ebs', 'rds', 's3', 'elbv2']] = Field(min_length=1, max_length=5)
    tag_filters: dict[str, str] = Field(default_factory=dict, max_length=10)

    @field_validator('regions')
    @classmethod
    def valid_regions(cls, values):
        import re
        if any(not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d+', value) or len(value) > 32 for value in values):
            raise ValueError('Use AWS region names such as us-east-1.')
        return list(dict.fromkeys(values))

    @field_validator('services')
    @classmethod
    def distinct_services(cls, values):
        return list(dict.fromkeys(values))

    @field_validator('tag_filters')
    @classmethod
    def valid_tags(cls, values):
        if any(not key or len(key) > 128 or len(value) > 256 for key, value in values.items()):
            raise ValueError('Tag keys must be 1–128 characters and values at most 256 characters.')
        return values


def token_for(user):
    now = datetime.now(timezone.utc)
    return {'access_token': jwt.encode({'sub': str(user.id), 'iat': now, 'exp': now + timedelta(hours=8)},
                                       JWT_SECRET, algorithm='HS256'), 'token_type': 'bearer'}


async def user_for_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], options={'require': ['exp', 'sub', 'iat']})
        user_id = int(payload['sub'])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(401, 'Invalid or expired token')
    async with Session() as session:
        user = await session.get(User, user_id)
    if not user:
        raise HTTPException(401, 'Invalid or expired token')
    return user


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Authentication required')
    return await user_for_token(credentials.credentials)


@app.get('/api/health')
async def health():
    async with Session() as session:
        await session.execute(select(1))
    return {'status': 'ok', 'mode': 'demo' if DEMO_MODE else 'live'}


@app.post('/api/auth/signup', status_code=201)
async def signup(body: Credentials):
    hashed = await asyncio.to_thread(bcrypt.hashpw, body.password.encode(), bcrypt.gensalt())
    async with Session() as session:
        user = User(email=body.email.lower(), password_hash=hashed.decode())
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(409, 'Email is already registered')
        return token_for(user)


@app.post('/api/auth/login')
async def login(body: Credentials):
    async with Session() as session:
        user = await session.scalar(select(User).where(User.email == body.email.lower()))
    # Perform the same expensive operation for unknown users to reduce timing differences.
    stored = user.password_hash.encode() if user else b'$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxAzqR.1LlbRb4M5LzFbqFTkS6u'
    valid = await asyncio.to_thread(bcrypt.checkpw, body.password.encode(), stored)
    if not user or not valid:
        raise HTTPException(401, 'Invalid email or password')
    return token_for(user)


@app.get('/api/scan-options')
async def scan_options(user=Depends(current_user)):
    try:
        return await aws_scanner.scan_options()
    except aws_scanner.ScanError as exc:
        raise HTTPException(502, str(exc))


def emit(identifier, message, status='running'):
    progress.setdefault(identifier, []).append({'message': message, 'status': status})


async def run_analysis(identifier, scan):
    try:
        async with Session() as session:
            row = await session.get(Analysis, identifier)
            row.status = 'running'
            await session.commit()
        emit(identifier, 'Verifying AWS account...')
        emit(identifier, 'Scanning selected regions and services...')
        inventory = await aws_scanner.scan_account(**scan)
        resources = inventory['resources']
        emit(identifier, 'Analyzing configuration with AI...')
        result = await ai_analyzer.analyze(resources)
        result['limitations'] = list(dict.fromkeys(result.get('limitations', []) + inventory['warnings'] + [
            'Configuration review only: billing, utilization, live pricing, and realized savings are not collected.'
        ]))
        emit(identifier, 'Storing results...')
        async with Session() as session:
            row = await session.get(Analysis, identifier)
            row.resources_scanned = len(resources)
            row.issues_found = len(result['issues'])
            row.estimated_savings = result['estimated_savings']
            row.analysis_result = result
            row.status = 'completed'
            await session.commit()
        emit(identifier, 'Analysis complete', 'completed')
    except Exception as exc:
        if isinstance(exc, (aws_scanner.ScanError, RuntimeError)):
            message = str(exc)
        elif 'openai' in type(exc).__module__:
            message = f'AI Error ({type(exc).__name__}): {exc}'
        else:
            message = f'Analysis failed: {exc}'
        logger.error('Analysis %s failed (%s: %s)', identifier, type(exc).__name__, exc)
        async with Session() as session:
            row = await session.get(Analysis, identifier)
            row.status = 'failed'
            row.analysis_result = {'error': message}
            await session.commit()
        emit(identifier, message, 'failed')
    finally:
        # Retain a bounded replay cache. Persistent status remains available via REST.
        if len(progress) > 200:
            for key in list(progress):
                if progress[key] and progress[key][-1]['status'] in ('completed', 'failed') and key != identifier:
                    progress.pop(key)
                    break


@app.post('/api/analyze', status_code=202)
async def start_analysis(body: AnalysisRequest, user=Depends(current_user)):
    # Bound local concurrency; production should use a durable queue and per-user rate limits.
    async with admission_lock:
        if len(tasks) >= 4:
            raise HTTPException(429, 'Server is busy. Try again shortly.')
        identifier = str(uuid4())
        async with Session() as session:
            scan = body.model_dump()
            scope = f"{body.account_id} · {', '.join(body.regions)}"
            session.add(Analysis(id=identifier, user_id=user.id, scope=scope[:128], scan_config=scan))
            await session.commit()
        progress[identifier] = []
        task = asyncio.create_task(run_analysis(identifier, scan))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
    return {'analysis_id': identifier, 'status': 'queued'}


@app.get('/api/history')
async def history(user=Depends(current_user)):
    async with Session() as session:
        rows = await session.scalars(select(Analysis).where(Analysis.user_id == user.id)
                                     .order_by(Analysis.created_at.desc()).limit(100))
        return [serialize(row) for row in rows]


@app.get('/api/analyses/{identifier}')
async def get_analysis(identifier: str, user=Depends(current_user)):
    async with Session() as session:
        row = await session.get(Analysis, identifier)
        if not row or row.user_id != user.id:
            raise HTTPException(404, 'Analysis not found')
        return serialize(row)


@app.get('/api/analyses/{identifier}/csv')
async def get_analysis_csv(identifier: str, user=Depends(current_user)):
    async with Session() as session:
        row = await session.get(Analysis, identifier)
        if not row or row.user_id != user.id:
            raise HTTPException(404, 'Analysis not found')
        if row.status != 'completed':
            raise HTTPException(400, 'Analysis is not completed yet')

        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow([
            'Resource Name', 'Issue Type', 'Severity', 'Estimated Savings',
            'Explanation', 'Recommended Fix Command', 'Account Scope',
            'Regions', 'Services', 'Resources Scanned', 'Issues Found', 'Scan Date'
        ])
        issues = (row.analysis_result or {}).get('issues', [])
        regions = '; '.join((row.scan_config or {}).get('regions', []))
        services = '; '.join((row.scan_config or {}).get('services', []))
        scan_date = row.created_at.isoformat() if row.created_at else ''

        if not issues:
            writer.writerow([
                'None', 'No Issues Detected', 'low', '$0.00',
                (row.analysis_result or {}).get('summary', 'No issues identified.'),
                'N/A', row.scope, regions, services,
                str(row.resources_scanned), str(row.issues_found), scan_date
            ])
        else:
            for issue in issues:
                writer.writerow([
                    issue.get('resource_name', ''),
                    issue.get('issue_type', ''),
                    issue.get('severity', ''),
                    issue.get('estimated_savings', ''),
                    issue.get('explanation', ''),
                    issue.get('fix_command', ''),
                    row.scope,
                    regions,
                    services,
                    str(row.resources_scanned),
                    str(row.issues_found),
                    scan_date
                ])

        csv_data = output.getvalue()
        clean_filename = f"cost-analysis-{row.id[:8]}.csv"
        return Response(
            content=csv_data,
            media_type='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{clean_filename}"'}
        )


@app.websocket('/ws/progress/{identifier}')
async def websocket_progress(socket: WebSocket, identifier: str):
    if socket.headers.get('origin') and socket.headers['origin'] not in CORS_ORIGINS:
        await socket.close(code=1008)
        return
    await socket.accept()
    try:
        # First-frame auth keeps bearer tokens out of access-log URLs.
        auth = await asyncio.wait_for(socket.receive_json(), timeout=10)
        user = await user_for_token(auth.get('token', ''))
        async with Session() as session:
            row = await session.get(Analysis, identifier)
            if not row or row.user_id != user.id:
                await socket.close(code=1008)
                return
        cursor = 0
        deadline = asyncio.get_running_loop().time() + 600
        while asyncio.get_running_loop().time() < deadline:
            events = progress.get(identifier, [])
            for event in events[cursor:]:
                await socket.send_json(event)
                cursor += 1
                if event['status'] in ('completed', 'failed'):
                    await socket.close()
                    return
            if identifier not in progress:
                async with Session() as session:
                    row = await session.get(Analysis, identifier)
                await socket.send_json({'message': row.analysis_result.get('error', 'Analysis ' + row.status), 'status': row.status})
                if row.status in ('completed', 'failed'):
                    await socket.close()
                    return
            await asyncio.sleep(0.25)
        await socket.close(code=1000)
    except (HTTPException, asyncio.TimeoutError, ValueError, AttributeError, TypeError):
        await socket.close(code=1008)
    except WebSocketDisconnect:
        pass
