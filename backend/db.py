import ssl
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import DATABASE_URL


def engine_options(url):
    options = {}
    if url.startswith(('postgres://', 'postgresql://', 'postgresql+asyncpg://')):
        url = url.replace('postgres://', 'postgresql+asyncpg://', 1).replace('postgresql://', 'postgresql+asyncpg://', 1)
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        mode = query.pop('sslmode', 'verify-full')
        if mode not in ('require', 'verify-full', 'verify-ca'):
            raise RuntimeError('PostgreSQL connections require TLS.')
        # Verify certificates and hostnames even when the URL requests sslmode=require.
        options['connect_args'] = {'ssl': ssl.create_default_context()}
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url, options


url, options = engine_options(DATABASE_URL)
engine = create_async_engine(url, **options)
Session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Analysis(Base):
    __tablename__ = 'analyses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    # Keep the existing column name so historical reports survive this scope change.
    scope: Mapped[str] = mapped_column('resource_group', String(128))
    scan_config: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, 'postgresql'), nullable=True)
    resources_scanned: Mapped[int] = mapped_column(Integer, default=0)
    issues_found: Mapped[int] = mapped_column(Integer, default=0)
    estimated_savings: Mapped[str] = mapped_column(Text, default='Not estimated')
    analysis_result: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, 'postgresql'), default=dict)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def serialize(row):
    result = {key: getattr(row, key) for key in (
        'id', 'scope', 'scan_config', 'resources_scanned', 'issues_found',
        'estimated_savings', 'analysis_result', 'status', 'created_at')}

    if result['created_at'].tzinfo is None:
        result['created_at'] = result['created_at'].replace(tzinfo=timezone.utc)
    return result


async def initialize_database():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        columns = await connection.run_sync(lambda sync: {column['name'] for column in inspect(sync).get_columns('analyses')})
        if 'scan_config' not in columns:
            # Additive, nullable migration: old rows remain readable without inventing scan settings.
            kind = 'JSONB' if connection.dialect.name == 'postgresql' else 'JSON'
            await connection.execute(text(f'ALTER TABLE analyses ADD COLUMN scan_config {kind}'))
