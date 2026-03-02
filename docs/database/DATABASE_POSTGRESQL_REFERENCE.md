# Cineca Agentic Platform - PostgreSQL Database Reference

**Last Updated:** 2025-10-24  
**Purpose:** Comprehensive reference for PostgreSQL relational database implementation

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
   - [Database Connection](#database-connection)
   - [Alembic Migrations](#alembic-migrations)
   - [ORM Models](#orm-models)
   - [Repositories](#repositories)
4. [Schema Overview](#schema-overview)
5. [Migration System](#migration-system)
6. [Best Practices](#best-practices)

---

## Overview

PostgreSQL is the primary relational database for the Cineca Agentic Platform, storing:

- **Multi-Tenancy**: Tenant configuration and isolation
- **LLM Providers**: OpenAI, Anthropic, Ollama provider configurations
- **Model Instances**: Deployed model instances with process management
- **Tools & MCP**: Tool registry and audit trail
- **Agent Sessions**: Conversation state and workflow steps
- **Jobs**: Background task tracking (optional, can use Redis)
- **Manifests**: Built-in model deployment configurations
- **Audit Trails**: Internal operations and administrative actions

**Technology Stack:**

- **Database:** PostgreSQL 15.x (ACID-compliant RDBMS)
- **ORM:** SQLAlchemy 2.x (declarative ORM with async support)
- **Migrations:** Alembic (schema version control)
- **Connection Pooling:** QueuePool (production) or NullPool (testing)
- **Python Driver:** psycopg2-binary

**Design Principles:**

- **Normalization**: 3NF schema design with foreign keys
- **JSONB Fields**: Flexible metadata storage
- **Timestamps**: created_at/updated_at on all tables
- **Soft Deletes**: Logical deletion where appropriate
- **Indexes**: Strategic indexing on lookup columns

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│              PostgreSQL Container (Port 5432)               │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │   Database: cineca_platform                           │ │
│  │                                                         │ │
│  │   Tables:                                             │ │
│  │   • tenants                                           │ │
│  │   • providers                                         │ │
│  │   • model_instances                                   │ │
│  │   • builtin_processes                                 │ │
│  │   • builtins_manifests                                │ │
│  │   • tools, tool_invocations, tool_audit_events        │ │
│  │   • agent_sessions, agent_steps, agent_runs           │ │
│  │   • jobs, job_events (optional)                       │ │
│  │   • user_default_models                               │ │
│  │   • internal_ops_events                               │ │
│  │   • idempotency_keys                                  │ │
│  │   • alembic_version (migration tracking)              │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         ↑                              ↑
         │ SQLAlchemy ORM               │ Alembic Migrations
         │                              │
    ┌────────────┐              ┌──────────────┐
    │  Database  │              │   Migration  │
    │   Engine   │              │    System    │
    └────────────┘              └──────────────┘
         ↑                              ↑
         │                              │
  ┌──────┴──────┐              ┌────────┴────────┐
  │ Repositories│              │ Alembic Versions│
  │  • Tenants  │              │  001_tenants    │
  │  • Providers│              │  002_tools      │
  │  • Agents   │              │  003_jobs       │
  │  • Jobs     │              │  004_providers  │
  │  • Tools    │              │  ...            │
  └─────────────┘              └─────────────────┘
```

### Data Flow

1. **Configuration** → `src/config.py` provides DATABASE_URL
2. **Engine Creation** → `db/postgres_control/database.py` creates SQLAlchemy engine
3. **Session Factory** → SessionLocal for dependency injection
4. **Migration Check** → Alembic ensures schema is up-to-date
5. **Repository Pattern** → Business logic uses repositories for data access
6. **Transaction Management** → Automatic commit/rollback via context managers

---

## Core Components

### Database Connection

**File:** `db/postgres_control/database.py`  
**Lines:** 150  
**Purpose:** SQLAlchemy engine, session factory, and health checks

#### Engine Configuration

```python
def create_db_engine() -> Engine:
    """
    Create SQLAlchemy engine with connection pooling.
    
    Features:
    - QueuePool for production (configurable size)
    - NullPool for testing (no pooling)
    - Pre-ping to detect stale connections
    - Statement timeout (30s)
    - SSL support via DB_SSLMODE
    
    Returns:
        Configured Engine instance
    """
    engine_config = {
        "echo": settings.DB_ECHO,  # Log SQL statements
        "pool_pre_ping": settings.DB_POOL_PRE_PING,  # Ping before use
        "pool_recycle": settings.DB_POOL_RECYCLE,  # Recycle connections
    }
    
    # Pool selection
    if settings.APP_ENV == "test":
        engine_config["poolclass"] = NullPool
    else:
        engine_config["poolclass"] = QueuePool
        engine_config["pool_size"] = settings.DB_POOL_SIZE  # Default: 5
        engine_config["max_overflow"] = settings.DB_POOL_SIZE * 2
        engine_config["pool_timeout"] = settings.DB_POOL_TIMEOUT
    
    # Connection arguments
    connect_args = {
        "options": "-c statement_timeout=30000"  # 30 seconds
    }
    
    if settings.DB_SSLMODE and settings.DB_SSLMODE != "disable":
        connect_args["sslmode"] = settings.DB_SSLMODE
    
    engine_config["connect_args"] = connect_args
    
    engine = create_engine(settings.database_url, **engine_config)
    
    logger.info(f"Database engine created: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    return engine
```

#### Session Management

```python
# Global engine instance
engine: Engine = create_db_engine()

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # Prevent lazy loading issues
)

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions.
    
    Usage:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for non-FastAPI code.
    
    Usage:
        with get_db_context() as db:
            items = db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

#### Health Check

```python
def check_db_health() -> tuple[bool, str | None]:
    """
    Check if database is reachable.
    
    Returns:
        (is_healthy, error_message)
    """
    try:
        with get_db_context() as db:
            db.execute(text("SELECT 1"))
        return (True, None)
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return (False, str(e))
```

#### Slow Query Logging

```python
@event.listens_for(engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, params, context, executemany):
    conn.info.setdefault("query_start_time", []).append(time.time())

@event.listens_for(engine, "after_cursor_execute")
def receive_after_cursor_execute(conn, cursor, statement, params, context, executemany):
    total = time.time() - conn.info["query_start_time"].pop()
    
    # Log slow queries (>200ms)
    if total > 0.2:
        logger.warning(f"Slow query detected ({total:.3f}s): {statement[:200]}...")
```

---

### Alembic Migrations

**File:** `db/postgres_control/alembic/env.py`  
**Lines:** 80  
**Purpose:** Alembic environment configuration for schema migrations

#### Configuration

```python
# Alembic Config object
config = context.config

# Set target metadata from Base
target_metadata = Base.metadata

# Override sqlalchemy.url with settings
config.set_main_option("sqlalchemy.url", settings.database_url)
```

#### Online Migrations

```python
def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    
    Creates engine and runs migrations in a transaction.
    """
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = settings.database_url
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No pooling for migrations
    )
    
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Detect type changes
            compare_server_default=True,  # Detect default changes
        )
        
        with context.begin_transaction():
            context.run_migrations()
```

#### Migration Commands

```bash
# Generate new migration
alembic revision --autogenerate -m "Add user_roles table"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1

# Show current version
alembic current

# Show migration history
alembic history
```

---

### ORM Models

**Directory:** `db/postgres_control/models/`  
**Files:** 14 model files  
**Purpose:** SQLAlchemy ORM models for database tables

#### Base Model Pattern

```python
from sqlalchemy import Column, String, DateTime, func
from db.postgres_control.database import Base

class BaseModel:
    """Base class with common fields."""
    
    id = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

#### Tenant Model

**File:** `db/postgres_control/models/tenant.py`

```python
class Tenant(Base):
    """
    Multi-tenant configuration.
    
    Stores tenant metadata, admin contact, and settings.
    """
    __tablename__ = "tenants"
    
    id = Column(String, primary_key=True)  # UUID
    name = Column(String, nullable=False, unique=True)
    admin_email = Column(String, nullable=False)
    metadata = Column(JSONB, default={})  # Flexible metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Indexes
    __table_args__ = (
        Index("idx_tenants_name", "name"),
        Index("idx_tenants_admin_email", "admin_email"),
    )
```

#### Provider Model

**File:** `db/postgres_control/models/provider.py`

```python
class Provider(Base):
    """
    LLM provider configuration (OpenAI, Anthropic, Ollama, etc.).
    """
    __tablename__ = "providers"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # openai, anthropic, ollama
    base_url = Column(String)
    api_key_encrypted = Column(String)  # Encrypted API key
    default_model = Column(String)
    metadata = Column(JSONB, default={})
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="providers")
    
    # Indexes
    __table_args__ = (
        Index("idx_providers_tenant_id", "tenant_id"),
        Index("idx_providers_type", "type"),
    )
```

#### Model Instance

**File:** `db/postgres_control/models/model_instance.py`

```python
class ModelInstance(Base):
    """
    Deployed model instance (e.g., locally running Ollama model).
    """
    __tablename__ = "model_instances"
    
    id = Column(String, primary_key=True)
    model_id = Column(String, nullable=False)  # Logical model ID
    provider_id = Column(String, ForeignKey("providers.id"), nullable=False)
    status = Column(String, nullable=False)  # active, stopped, error
    endpoint_url = Column(String)
    metadata = Column(JSONB, default={})
    tenant_id = Column(String, ForeignKey("tenants.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    provider = relationship("Provider", back_populates="instances")
    tenant = relationship("Tenant")
    
    # Indexes
    __table_args__ = (
        Index("idx_model_instances_provider_id", "provider_id"),
        Index("idx_model_instances_status", "status"),
    )
```

#### Agent Session

**File:** `db/postgres_control/models/agent_session.py`

```python
class AgentSession(Base):
    """
    Multi-turn agent conversation session.
    """
    __tablename__ = "agent_sessions"
    
    session_id = Column(String, primary_key=True)
    owner = Column(String, nullable=False)  # User principal
    tenant_id = Column(String, ForeignKey("tenants.id"))
    status = Column(String, nullable=False)  # active, completed, cancelled
    manager = Column(String)  # LLM manager name
    tools = Column(ARRAY(String), default=[])
    temperature = Column(Float, default=0.7)
    max_steps = Column(Integer, default=10)
    last_step_seq = Column(Integer, default=0)  # Monotonic step counter
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    steps = relationship("AgentStep", back_populates="session", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("idx_agent_sessions_owner", "owner"),
        Index("idx_agent_sessions_status", "status"),
        Index("idx_agent_sessions_tenant_id", "tenant_id"),
    )
```

#### Agent Step

**File:** `db/postgres_control/models/agent_step.py`

```python
class AgentStep(Base):
    """
    Individual step in agent conversation (message, tool call, etc.).
    """
    __tablename__ = "agent_steps"
    
    step_id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("agent_sessions.session_id"), nullable=False)
    seq = Column(Integer, nullable=False)  # Sequential order within session
    type = Column(String, nullable=False)  # message, user, assistant, tool, system, error
    message = Column(Text)
    tool = Column(String)
    input = Column(JSONB)
    output = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    session = relationship("AgentSession", back_populates="steps")
    
    # Indexes
    __table_args__ = (
        Index("idx_agent_steps_session_id", "session_id"),
        Index("idx_agent_steps_session_seq", "session_id", "seq"),
    )
```

#### Tool Model

**File:** `db/postgres_control/models/tool.py`

```python
class Tool(Base):
    """
    MCP tool registry.
    """
    __tablename__ = "tools"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text)
    input_schema = Column(JSONB)  # JSON schema for tool input
    metadata = Column(JSONB, default={})
    tenant_id = Column(String, ForeignKey("tenants.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    invocations = relationship("ToolInvocation", back_populates="tool")
    
    # Indexes
    __table_args__ = (
        Index("idx_tools_name", "name"),
        Index("idx_tools_tenant_id", "tenant_id"),
    )
```

#### Job Model

**File:** `db/postgres_control/models/job.py`

```python
class Job(Base):
    """
    Background job tracking (alternative to Redis storage).
    """
    __tablename__ = "jobs"
    
    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False)  # queued, running, finished, failed, cancelled
    owner = Column(String, nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id"))
    payload = Column(JSONB)  # Input parameters
    result = Column(JSONB)  # Output result
    error = Column(Text)  # Error message if failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    events = relationship("JobEvent", back_populates="job", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("idx_jobs_owner", "owner"),
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_type", "type"),
        Index("idx_jobs_created_at", "created_at"),
    )
```

---

### Repositories

**Directory:** `db/postgres_control/repositories/`  
**Files:** 9 repository files  
**Purpose:** Data access layer with business logic

#### Repository Pattern

```python
class BaseRepository:
    """Base repository with common CRUD operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get(self, id: str) -> Optional[Model]:
        """Get by ID."""
        return self.db.query(Model).filter(Model.id == id).first()
    
    def create(self, **kwargs) -> Model:
        """Create new record."""
        instance = Model(**kwargs)
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance
    
    def update(self, id: str, **kwargs) -> Optional[Model]:
        """Update existing record."""
        instance = self.get(id)
        if not instance:
            return None
        
        for key, value in kwargs.items():
            setattr(instance, key, value)
        
        self.db.commit()
        self.db.refresh(instance)
        return instance
    
    def delete(self, id: str) -> bool:
        """Delete record."""
        instance = self.get(id)
        if not instance:
            return False
        
        self.db.delete(instance)
        self.db.commit()
        return True
```

#### Tenants Repository

**File:** `db/postgres_control/repositories/tenants.py`

```python
class TenantsRepository:
    """Repository for tenant CRUD operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(
        self,
        name: str,
        admin_email: str,
        metadata: dict = {},
    ) -> Tuple[Tenant, bool]:
        """
        Create tenant (idempotent).
        
        Returns:
            (tenant, was_created)
        """
        # Check if exists
        existing = self.db.query(Tenant).filter(Tenant.name == name).first()
        if existing:
            return (existing, False)
        
        # Create new
        tenant = Tenant(
            id=str(uuid.uuid4()),
            name=name,
            admin_email=admin_email,
            metadata=metadata,
        )
        
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        
        return (tenant, True)
    
    def list_all(self) -> List[Tenant]:
        """List all tenants."""
        return self.db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    
    def get_by_name(self, name: str) -> Optional[Tenant]:
        """Get tenant by name."""
        return self.db.query(Tenant).filter(Tenant.name == name).first()
```

#### Agents Repository

**File:** `db/postgres_control/repositories/agents.py`

```python
class AgentsRepository:
    """Repository for agent sessions and steps."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_session(
        self,
        session_id: str,
        owner: str,
        tenant_id: Optional[str] = None,
        **kwargs
    ) -> AgentSession:
        """Create new agent session."""
        session = AgentSession(
            session_id=session_id,
            owner=owner,
            tenant_id=tenant_id,
            **kwargs
        )
        
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        
        return session
    
    def add_step(
        self,
        session_id: str,
        step_id: str,
        type: str,
        **kwargs
    ) -> AgentStep:
        """
        Add step to session.
        
        Auto-increments seq counter on session.
        """
        session = self.db.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()
        
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Increment sequence
        session.last_step_seq += 1
        seq = session.last_step_seq
        
        step = AgentStep(
            step_id=step_id,
            session_id=session_id,
            seq=seq,
            type=type,
            **kwargs
        )
        
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        
        return step
    
    def list_sessions(
        self,
        owner: str,
        limit: int = 25,
        offset: int = 0
    ) -> Tuple[List[AgentSession], int]:
        """
        List sessions for owner with pagination.
        
        Returns:
            (sessions, total_count)
        """
        query = self.db.query(AgentSession).filter(AgentSession.owner == owner)
        
        total = query.count()
        
        sessions = query.order_by(
            AgentSession.created_at.desc()
        ).limit(limit).offset(offset).all()
        
        return (sessions, total)
```

#### Provider Repository

**File:** `db/postgres_control/repositories/provider_repo.py`

```python
class ProviderRepository:
    """Repository for LLM provider management."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_provider(
        self,
        id: str,
        name: str,
        type: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        tenant_id: Optional[str] = None,
        **kwargs
    ) -> Provider:
        """Create new provider."""
        # Encrypt API key if provided
        api_key_encrypted = encrypt_api_key(api_key) if api_key else None
        
        provider = Provider(
            id=id,
            name=name,
            type=type,
            base_url=base_url,
            api_key_encrypted=api_key_encrypted,
            tenant_id=tenant_id,
            **kwargs
        )
        
        self.db.add(provider)
        self.db.commit()
        self.db.refresh(provider)
        
        return provider
    
    def list_providers(
        self,
        tenant_id: Optional[str] = None,
        type: Optional[str] = None
    ) -> List[Provider]:
        """List providers with optional filters."""
        query = self.db.query(Provider)
        
        if tenant_id:
            query = query.filter(Provider.tenant_id == tenant_id)
        
        if type:
            query = query.filter(Provider.type == type)
        
        return query.order_by(Provider.created_at.desc()).all()
    
    def get_decrypted_api_key(self, provider_id: str) -> Optional[str]:
        """Get decrypted API key for provider."""
        provider = self.db.query(Provider).filter(Provider.id == provider_id).first()
        
        if not provider or not provider.api_key_encrypted:
            return None
        
        return decrypt_api_key(provider.api_key_encrypted)
```

---

## Schema Overview

### Entity-Relationship Diagram

```
┌─────────────┐         ┌──────────────┐         ┌────────────────┐
│   Tenants   │◄───────┤   Providers  │◄───────┤ Model Instances│
│             │         │              │         │                │
│ • id        │         │ • id         │         │ • id           │
│ • name      │         │ • type       │         │ • model_id     │
│ • admin_email│        │ • base_url   │         │ • status       │
│ • metadata  │         │ • api_key    │         │ • endpoint_url │
└─────────────┘         └──────────────┘         └────────────────┘
       │                        │
       │                        │
       ▼                        ▼
┌─────────────┐         ┌──────────────┐
│    Tools    │         │ Builtin      │
│             │         │ Processes    │
│ • id        │         │              │
│ • name      │         │ • id         │
│ • description│        │ • manifest_id│
│ • input_schema│       │ • status     │
└─────────────┘         │ • pid        │
       │                └──────────────┘
       │
       ▼
┌─────────────┐
│   Tool      │
│ Invocations │
│             │
│ • id        │
│ • tool_id   │
│ • input     │
│ • output    │
│ • status    │
└─────────────┘

┌──────────────┐         ┌──────────────┐
│ Agent        │◄───────┤ Agent Steps  │
│ Sessions     │         │              │
│              │         │ • step_id    │
│ • session_id │         │ • session_id │
│ • owner      │         │ • seq        │
│ • status     │         │ • type       │
│ • tools      │         │ • message    │
│ • last_step_seq│       │ • tool       │
└──────────────┘         └──────────────┘

┌──────────────┐
│ Agent Runs   │
│              │
│ • run_id     │
│ • session_id │
│ • prompt     │
│ • output     │
│ • trace_id   │
└──────────────┘

┌──────────────┐         ┌──────────────┐
│    Jobs      │◄───────┤ Job Events   │
│              │         │              │
│ • id         │         │ • id         │
│ • type       │         │ • job_id     │
│ • status     │         │ • event_type │
│ • owner      │         │ • data       │
│ • payload    │         │ • timestamp  │
│ • result     │         └──────────────┘
└──────────────┘
```

### Table Summary

| Table | Purpose | Key Columns | Indexes |
|-------|---------|-------------|---------|
| `tenants` | Multi-tenant configuration | id, name, admin_email | name, admin_email |
| `providers` | LLM provider configs | id, type, base_url | type, tenant_id |
| `model_instances` | Deployed model instances | id, provider_id, status | provider_id, status |
| `builtin_processes` | Built-in model processes | id, manifest_id, status, pid | manifest_id, status |
| `builtins_manifests` | Deployment manifests | id, model_id, image_name | model_id |
| `tools` | MCP tool registry | id, name, input_schema | name, tenant_id |
| `tool_invocations` | Tool execution history | id, tool_id, status | tool_id, status |
| `tool_audit_events` | Tool audit trail | id, tool_id, action | tool_id, created_at |
| `agent_sessions` | Agent conversations | session_id, owner, status | owner, status |
| `agent_steps` | Conversation steps | step_id, session_id, seq | session_id+seq |
| `agent_runs` | One-shot agent runs | run_id, session_id | session_id |
| `jobs` | Background tasks | id, type, status, owner | owner, status, type |
| `job_events` | Job event stream | id, job_id, event_type | job_id, created_at |
| `user_default_models` | User model preferences | user_id, provider_id | user_id |
| `internal_ops_events` | Admin audit trail | id, action, actor | action, created_at |
| `idempotency_keys` | Idempotency tracking | key, job_id, expires_at | key, expires_at |

---

## Migration System

### Migration Files

**Directory:** `db/postgres_control/alembic/versions/`

**001_initial_tenants_table.py** - Create tenants table
**002_create_tools_tables.py** - Create tools, tool_invocations, tool_audit_events
**003_create_jobs_tables.py** - Create jobs, job_events
**004_create_providers_tables.py** - Create providers table
**005_create_builtins_manifests_tables.py** - Create builtins_manifests
**006_create_model_instances_tables.py** - Create model_instances
**007_user_default_models.py** - Create user_default_models
**008_create_agent_tables.py** - Create agent_sessions, agent_steps, agent_runs
**009_add_last_step_seq_to_agent_sessions.py** - Add last_step_seq counter
**010_allow_message_step_type.py** - Add message type to steps
**011_create_builtin_process_tables.py** - Create builtin_processes
**012_create_internal_ops_events.py** - Create internal_ops_events

### Migration Workflow

```bash
# 1. Create new migration
cd db/postgres_control
alembic revision --autogenerate -m "Add user_roles table"

# 2. Review generated migration
# Edit alembic/versions/{revision}_add_user_roles_table.py

# 3. Test migration (upgrade)
alembic upgrade head

# 4. Test rollback
alembic downgrade -1

# 5. Apply in production
alembic upgrade head
```

### Sample Migration

```python
# alembic/versions/013_add_user_roles.py

from alembic import op
import sqlalchemy as sa

revision = '013'
down_revision = '012'

def upgrade():
    op.create_table(
        'user_roles',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_user_roles_user_id', 'user_id'),
    )

def downgrade():
    op.drop_table('user_roles')
```

---

## Best Practices

### 1. Always Use Transactions

```python
# Good: Explicit transaction
with get_db_context() as db:
    try:
        # Multiple operations
        tenant = Tenant(...)
        db.add(tenant)
        
        provider = Provider(tenant_id=tenant.id, ...)
        db.add(provider)
        
        db.commit()
    except:
        db.rollback()
        raise

# Bad: Auto-commit per operation
db.add(tenant)
db.commit()  # Committed even if provider fails
db.add(provider)
db.commit()
```

### 2. Use Indexes Strategically

```python
# Good: Index on frequently queried columns
__table_args__ = (
    Index('idx_jobs_owner', 'owner'),
    Index('idx_jobs_status', 'status'),
    Index('idx_jobs_created_at', 'created_at'),
)

# Bad: No indexes on lookup columns
# Queries will be slow on large tables
```

### 3. Avoid N+1 Queries

```python
# Good: Eager loading
sessions = db.query(AgentSession).options(
    joinedload(AgentSession.steps)
).filter(AgentSession.owner == owner).all()

# Bad: Lazy loading in loop
sessions = db.query(AgentSession).filter(AgentSession.owner == owner).all()
for session in sessions:
    steps = session.steps  # Triggers separate query!
```

### 4. Use JSONB for Flexible Data

```python
# Good: JSONB for extensible metadata
class Provider(Base):
    metadata = Column(JSONB, default={})

# Query JSONB
providers = db.query(Provider).filter(
    Provider.metadata['region'].astext == 'us-east-1'
).all()
```

### 5. Handle Concurrent Updates

```python
# Good: Optimistic locking with version column
class Job(Base):
    version = Column(Integer, default=1)

def update_job(db, job_id, new_status):
    job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
    
    job.status = new_status
    job.version += 1
    
    db.commit()
```

### 6. Monitor Connection Pool

```python
# Check pool status
pool = engine.pool
print(f"Pool size: {pool.size()}")
print(f"Checked out: {pool.checkedout()}")
print(f"Overflow: {pool.overflow()}")

# Log pool events
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    logger.debug("New database connection")
```

---

**Document Version:** 1.0  
**Last Updated:** 2025-10-24  
**Maintainer:** Cineca Agentic Platform Team
