---
title: Dockerize Personal Assistant Application
type: feat
date: 2026-02-15
complexity: high
estimated_effort: 3-5 days
---

# Dockerize Personal Assistant Application

## Overview

Transform the Personal Assistant application into a production-ready containerized deployment supporting both local development and cloud environments. This includes multi-stage Docker builds, secrets management, health checks, database flexibility (SQLite/PostgreSQL), and comprehensive security hardening.

**Target Environments:**
- Local development (Docker Compose + SQLite)
- Cloud deployment (AWS/GCP/Azure + PostgreSQL)
- CI/CD pipelines (automated testing and deployment)

**Key Goals:**
- ✅ Fast startup and rebuild times (< 30 seconds for code changes)
- ✅ Minimal production image size (< 200MB)
- ✅ Secure secrets management (no credentials in images)
- ✅ Comprehensive health checks and monitoring
- ✅ Zero-downtime deployments with database migrations

---

## Problem Statement

### Current State

The Personal Assistant application currently runs only in local development environments with:
- Manual Python virtual environment setup
- File-based configuration with embedded secrets
- SQLite database in working directory
- Background agent managed via PID files
- OAuth tokens stored in local config files
- Platform-specific features (macOS menu bar, native notifications)

### Challenges for Containerization

**1. Ephemeral Filesystem vs Persistent Configuration**
- App stores OAuth tokens in `config.yaml` (file-based)
- Docker containers have ephemeral filesystems by default
- Tokens must persist across container restarts

**2. Multi-Process Architecture**
- FastAPI API server (Uvicorn)
- Background agent (APScheduler)
- CLI tool (`pa` command)
- No existing process supervision for containers

**3. OAuth Authentication Flow**
- Interactive `pa accounts authenticate` requires browser
- No browser available in production containers
- Multiple Google accounts need separate OAuth flows

**4. Database Migration Strategy**
- Alembic migrations must run before app starts
- Multiple containers starting simultaneously = race conditions
- Failed migrations need graceful handling

**5. Platform-Specific Features**
- macOS menu bar app (PyObjC) incompatible with Linux containers
- Native notifications via `osascript` (macOS-only)
- Need fallback behaviors for containerized deployment

### Why This Matters

**For Developers:**
- Consistent environment across team (no "works on my machine")
- Faster onboarding (docker-compose up vs manual setup)
- Easy testing of production-like configurations

**For Operations:**
- Reproducible deployments
- Horizontal scaling capability
- Simplified rollbacks and updates
- Better resource utilization

**For End Users:**
- Higher availability (container orchestration)
- Faster updates (automated deployments)
- More reliable service (health checks, auto-restart)

---

## Proposed Solution

### Architecture Overview

**Multi-Container Architecture** (Recommended)

```
┌─────────────────────────────────────────────────────────────────┐
│                         Docker Compose                           │
│                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   API Server    │  │  Background     │  │   PostgreSQL    │ │
│  │                 │  │     Agent       │  │    Database     │ │
│  │  • FastAPI      │  │  • APScheduler  │  │                 │ │
│  │  • Uvicorn      │  │  • Email poller │  │  • Port 5432    │ │
│  │  • Port 8000    │  │  • LLM calls    │  │  • Volume mount │ │
│  │  • Health check │  │  • Task creator │  │  • Backups      │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                     │                     │          │
│           └─────────────────────┴─────────────────────┘          │
│                          Shared Network                          │
│                    (PostgreSQL connection)                       │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      Shared Volumes                          ││
│  │  • postgres_data: Database files                             ││
│  │  • app_data: SQLite for dev, application state              ││
│  │  • oauth_tokens: Persistent OAuth credentials               ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**Container Responsibilities:**

| Container | Purpose | Entry Point | Health Check |
|-----------|---------|-------------|--------------|
| `api` | FastAPI API server | `uvicorn src.api.main:app` | `GET /health` |
| `agent` | Background poller | `pa agent start --foreground` | Process alive |
| `db` | PostgreSQL database | `postgres` | `pg_isready` |
| `cli` | On-demand CLI | `pa` (interactive) | N/A |

### Key Architectural Decisions

#### Decision 1: OAuth Token Persistence Strategy

**Problem:** OAuth tokens must persist across container restarts and be writable (automatic refresh).

**Solution:** **Hybrid Approach**
1. **Development:** Volume-mount `config.yaml` for read/write access
2. **Production:** Store tokens in database + environment variable fallback

```python
# New: src/models/oauth_token.py
class OAuthToken(Base):
    """OAuth tokens stored in database for production."""
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(100), unique=True)
    provider: Mapped[str] = mapped_column(String(50))  # "google", "slack"
    access_token: Mapped[str] = mapped_column(String(2000))
    refresh_token: Mapped[str | None] = mapped_column(String(2000))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    token_data: Mapped[str | None] = mapped_column(Text)  # JSON blob
```

**Benefits:**
- Tokens persist across container restarts (database volume)
- Automatic refresh works (writes to database)
- No filesystem dependencies in production
- Backwards compatible (file-based config still works in dev)

#### Decision 2: Production OAuth Authentication Workflow

**Problem:** `pa accounts authenticate` requires browser interaction, unavailable in containers.

**Solution:** **API-Based OAuth Callback Endpoint**

```python
# New: src/api/routes/oauth.py
@router.get("/oauth/initiate")
async def initiate_oauth(account_id: str, provider: str):
    """Step 1: Generate OAuth URL for user to visit."""
    oauth_url = generate_oauth_url(account_id, provider)
    return {
        "oauth_url": oauth_url,
        "instructions": "Visit this URL to authenticate, then return to /oauth/status"
    }

@router.get("/oauth/callback")
async def oauth_callback(code: str, state: str):
    """Step 2: Handle OAuth callback and store tokens."""
    tokens = exchange_code_for_tokens(code, state)
    store_tokens_in_database(tokens)
    return {"status": "authenticated", "account_id": decode_state(state)}

@router.get("/oauth/status/{account_id}")
async def oauth_status(account_id: str):
    """Check if account is authenticated."""
    token = get_token_from_database(account_id)
    return {"authenticated": token is not None, "expires_at": token.expires_at}
```

**Workflow:**
1. Operator calls `GET /oauth/initiate?account_id=work&provider=google`
2. API returns OAuth URL
3. Operator opens URL in browser, completes OAuth
4. Google redirects to `http://api:8000/oauth/callback?code=...`
5. API stores tokens in database
6. Agent reads tokens from database on next poll

**Alternative (Simpler):** Pre-authenticate on local machine, export tokens as Docker secrets.

#### Decision 3: Agent Process Management

**Problem:** Agent must run continuously but not interfere with API server health.

**Solution:** **Separate Containers** (Recommended)

**Rationale:**
- ✅ Isolation: Agent crash doesn't affect API
- ✅ Independent scaling: Scale API horizontally, keep agent singleton
- ✅ Simplified health checks: Each container monitors one process
- ✅ Easier debugging: Logs separated by container

**Agent Singleton Enforcement:**
```yaml
# docker-compose.yml
services:
  agent:
    deploy:
      replicas: 1  # Enforce single instance
    restart: unless-stopped
```

**Alternative (If Single-Container Required):**
Use `supervisord` to manage both processes (see Alternative Approaches section).

#### Decision 4: Database Migration Execution

**Problem:** Alembic migrations must run exactly once before all containers start.

**Solution:** **Dedicated Migration Service with Dependency Chain**

```yaml
# docker-compose.yml
services:
  db:
    # PostgreSQL database
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 10s

  migrations:
    build: .
    command: ["alembic", "upgrade", "head"]
    depends_on:
      db:
        condition: service_healthy
    # Runs once, exits on completion

  api:
    build: .
    depends_on:
      migrations:
        condition: service_completed_successfully
      db:
        condition: service_healthy

  agent:
    build: .
    depends_on:
      migrations:
        condition: service_completed_successfully
      db:
        condition: service_healthy
```

**Benefits:**
- No race conditions (migrations run sequentially)
- Failed migrations prevent app containers from starting
- Clean separation of concerns
- Idempotent (safe to re-run)

**Failure Handling:**
```bash
#!/bin/bash
# entrypoint.sh for migrations container

set -e  # Exit on error

echo "Waiting for database to be ready..."
python -c "
import time
from sqlalchemy import create_engine
for i in range(30):
    try:
        create_engine('$DATABASE_URL').connect()
        break
    except:
        time.sleep(1)
else:
    exit(1)
"

echo "Running migrations..."
if ! alembic upgrade head; then
    echo "ERROR: Migration failed"
    echo "Database may be in inconsistent state"
    echo "Manual intervention required: alembic current && alembic history"
    exit 1
fi

echo "Migrations completed successfully"
```

#### Decision 5: SQLite vs PostgreSQL

**Problem:** SQLite has concurrency limitations with multiple containers.

**Solution:** **Support Both, Recommend PostgreSQL for Production**

| Feature | SQLite (Dev) | PostgreSQL (Prod) |
|---------|--------------|-------------------|
| Concurrent writes | ❌ Locks entire DB | ✅ Row-level locks |
| Network access | ❌ File-based only | ✅ TCP/IP |
| Scaling | ❌ Single container | ✅ Multi-container |
| Backup | File copy | pg_dump, snapshots |
| **Recommendation** | Local dev only | Production required |

**Configuration:**
```python
# src/utils/config.py
def get_database_url() -> str:
    """Get database URL based on environment."""
    if os.getenv("DATABASE_URL"):
        return os.getenv("DATABASE_URL")  # PostgreSQL from env
    elif os.getenv("ENV") == "production":
        raise ValueError("Production requires DATABASE_URL environment variable")
    else:
        return "sqlite:////app/data/personal_assistant.db"  # SQLite for dev
```

**Connection Pooling (PostgreSQL Only):**
```python
# src/models/database.py
if "postgresql" in database_url:
    engine = create_engine(
        database_url,
        pool_size=20,           # Persistent connections
        max_overflow=10,        # Burst capacity
        pool_recycle=3600,      # Recycle after 1 hour
        pool_pre_ping=True,     # Test before checkout
        echo=False              # Disable SQL logging in prod
    )
else:
    engine = create_engine(database_url)  # SQLite (no pooling)
```

#### Decision 6: Health Check Implementation

**Problem:** Need to validate entire system health, not just API process.

**Solution:** **Tiered Health Endpoints**

```python
# src/api/routes/health.py
from fastapi import APIRouter, status, Depends
from sqlalchemy import text
from src.models.database import get_db_session

router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
async def liveness_probe():
    """Liveness: Is the API process running?"""
    return {"status": "alive"}

@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_probe(db: Session = Depends(get_db_session)):
    """Readiness: Can the API handle traffic?"""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {str(e)}"
        )

@router.get("/health/agent", status_code=status.HTTP_200_OK)
async def agent_health_check(db: Session = Depends(get_db_session)):
    """Agent health: Is the background agent functioning?"""
    from src.models.agent_log import AgentLog

    # Check if agent logged activity in last 30 minutes
    last_log = db.query(AgentLog).order_by(AgentLog.timestamp.desc()).first()
    if not last_log:
        return {"status": "unknown", "message": "No agent logs found"}

    time_since_last = datetime.now() - last_log.timestamp
    if time_since_last.total_seconds() > 1800:  # 30 minutes
        return {
            "status": "stale",
            "last_activity": last_log.timestamp.isoformat(),
            "message": "Agent may be stuck or crashed"
        }, 503

    return {
        "status": "healthy",
        "last_activity": last_log.timestamp.isoformat(),
        "last_action": last_log.action
    }
```

**Docker Health Checks:**
```dockerfile
# Dockerfile (API container)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; exit(0 if requests.get('http://localhost:8000/health').status_code == 200 else 1)" || exit 1
```

```yaml
# docker-compose.yml
services:
  api:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/ready"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  agent:
    healthcheck:
      test: ["CMD", "pgrep", "-f", "pa agent"]
      interval: 60s
      timeout: 10s
      retries: 3
```

#### Decision 7: Secrets Management

**Problem:** API keys, OAuth tokens, database credentials must be secure.

**Solution:** **Layered Secrets Strategy**

**Development (docker-compose):**
```yaml
# docker-compose.yml
services:
  api:
    environment:
      - LLM_API_KEY=${LLM_API_KEY}  # From .env file
      - DATABASE_URL=${DATABASE_URL}
    env_file:
      - .env  # Git-ignored
```

**Production (Docker Secrets):**
```yaml
# docker-compose.prod.yml
services:
  api:
    secrets:
      - llm_api_key
      - google_oauth_credentials
    environment:
      - LLM_API_KEY_FILE=/run/secrets/llm_api_key

secrets:
  llm_api_key:
    external: true  # Created with: docker secret create llm_api_key -
  google_oauth_credentials:
    external: true
```

**Application Code:**
```python
# src/utils/config.py
def load_secret(name: str, env_var: str) -> str:
    """Load secret from Docker secret file or environment variable."""
    secret_file = Path(f"/run/secrets/{name}")
    env_file_var = f"{env_var}_FILE"

    # Priority: 1. Docker secret file, 2. Environment variable with _FILE suffix, 3. Direct env var
    if secret_file.exists():
        return secret_file.read_text().strip()
    elif os.getenv(env_file_var):
        return Path(os.getenv(env_file_var)).read_text().strip()
    elif os.getenv(env_var):
        return os.getenv(env_var)
    else:
        return ""

# Usage
llm_api_key = load_secret("llm_api_key", "LLM_API_KEY")
```

**Cloud Provider Patterns:**
- **AWS:** Use AWS Secrets Manager + IAM roles
- **GCP:** Use Google Secret Manager + service accounts
- **Azure:** Use Azure Key Vault + managed identities

#### Decision 8: Platform-Specific Features

**Problem:** macOS menu bar app and native notifications don't work in Linux containers.

**Solution:** **Feature Detection with Graceful Fallback**

```python
# src/utils/platform.py
import platform
import os

def is_containerized() -> bool:
    """Detect if running in Docker container."""
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")

def is_macos() -> bool:
    """Check if running on macOS."""
    return platform.system() == "Darwin"

def can_use_native_notifications() -> bool:
    """Check if native notifications are available."""
    return is_macos() and not is_containerized()

def can_use_menu_bar_app() -> bool:
    """Check if menu bar app is available."""
    return is_macos() and not is_containerized()
```

```python
# src/services/notification_service.py
def send_notification(self, title: str, message: str):
    """Send notification with platform detection."""
    if can_use_native_notifications():
        # Use macOS osascript
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "{title}"'
        ])
    else:
        # Fallback: Rich terminal output
        console.print(Panel(f"[bold]{title}[/bold]\n{message}", style="cyan"))
```

**Feature Availability Matrix:**

| Feature | macOS Local | Docker (macOS) | Docker (Linux) | Cloud |
|---------|-------------|----------------|----------------|-------|
| CLI (`pa`) | ✅ | ✅ | ✅ | ✅ |
| API server | ✅ | ✅ | ✅ | ✅ |
| Background agent | ✅ | ✅ | ✅ | ✅ |
| Native notifications | ✅ | ❌ | ❌ | ❌ |
| Terminal notifications | ✅ | ✅ | ✅ | ✅ |
| Menu bar app | ✅ | ❌ | ❌ | ❌ |
| Voice input | ✅ | ⚠️ (needs config) | ⚠️ | ❌ |

---

## Technical Approach

### Implementation Phases

#### Phase 1: Foundation (Days 1-2)

**Goal:** Basic containerization with SQLite for development.

**Deliverables:**

1. **Multi-Stage Dockerfile**
   ```dockerfile
   # Dockerfile
   # Stage 1: Builder
   FROM python:3.11-slim AS builder

   WORKDIR /app

   RUN apt-get update && apt-get install -y --no-install-recommends \
       gcc g++ portaudio19-dev libsndfile1-dev \
       && rm -rf /var/lib/apt/lists/*

   COPY pyproject.toml setup.py ./
   COPY src/ ./src/

   RUN pip install --no-cache-dir --prefix=/install .

   # Stage 2: Runtime
   FROM python:3.11-slim

   WORKDIR /app

   RUN apt-get update && apt-get install -y --no-install-recommends \
       curl libpq5 portaudio19-dev libsndfile1 \
       && rm -rf /var/lib/apt/lists/*

   COPY --from=builder /install /usr/local
   COPY --from=builder /app /app

   RUN groupadd -r appuser && useradd -r -g appuser appuser && \
       mkdir -p /app/data /app/.credentials && \
       chown -R appuser:appuser /app

   USER appuser

   EXPOSE 8000

   HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
       CMD curl --fail http://localhost:8000/health || exit 1

   CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

2. **Basic docker-compose.yml**
   ```yaml
   version: '3.8'

   services:
     api:
       build: .
       ports:
         - "8000:8000"
       environment:
         - DATABASE_URL=sqlite:////app/data/personal_assistant.db
         - LLM_API_KEY=${LLM_API_KEY}
       volumes:
         - app_data:/app/data
         - ./config.yaml:/app/config.yaml:ro
       command: ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

     agent:
       build: .
       environment:
         - DATABASE_URL=sqlite:////app/data/personal_assistant.db
         - LLM_API_KEY=${LLM_API_KEY}
       volumes:
         - app_data:/app/data
         - ./config.yaml:/app/config.yaml:ro
       command: ["pa", "agent", "start", "--foreground"]

   volumes:
     app_data:
   ```

3. **.dockerignore**
   ```
   # Python
   __pycache__/
   *.py[cod]
   *$py.class
   *.so
   .Python
   build/
   develop-eggs/
   dist/
   downloads/
   eggs/
   .eggs/
   lib/
   lib64/
   parts/
   sdist/
   var/
   wheels/
   *.egg-info/
   .installed.cfg
   *.egg

   # Virtual environments
   venv/
   ENV/
   env/
   .venv

   # IDE
   .vscode/
   .idea/
   *.swp
   *.swo
   *~

   # Testing
   .pytest_cache/
   .coverage
   htmlcov/

   # Git
   .git/
   .gitignore

   # Documentation
   docs/
   *.md

   # Secrets and config
   config.yaml
   credentials*.json
   token*.json
   .env

   # Database
   *.db
   *.db-shm
   *.db-wal

   # Logs
   *.log

   # macOS
   .DS_Store
   ```

4. **.env.example**
   ```bash
   # LLM Configuration
   LLM_API_KEY=sk-your-openai-key-here
   LLM_BASE_URL=https://api.openai.com/v1
   LLM_MODEL=gpt-4

   # Database (development uses SQLite, production uses PostgreSQL)
   DATABASE_URL=sqlite:////app/data/personal_assistant.db

   # Agent Configuration
   AGENT_POLL_INTERVAL=15
   AGENT_AUTONOMY_LEVEL=suggest

   # Environment
   ENV=development
   ```

**Acceptance Criteria:**
- [ ] `docker build .` succeeds and creates image < 200MB
- [ ] `docker-compose up` starts both API and agent containers
- [ ] API accessible at `http://localhost:8000`
- [ ] Health check `/health` returns 200
- [ ] Database persists after `docker-compose down && docker-compose up`
- [ ] CLI works: `docker-compose exec api pa tasks list`

#### Phase 2: Health Checks & Monitoring (Day 2)

**Goal:** Implement comprehensive health checks and logging.

**Deliverables:**

1. **Health Check Endpoints**
   - File: `src/api/routes/health.py`
   - Endpoints: `/health`, `/health/ready`, `/health/agent`
   - Integration with FastAPI main app

2. **Structured Logging**
   ```python
   # src/utils/logging_config.py
   import logging
   import sys

   def setup_logging():
       """Configure logging for containerized environment."""
       logging.basicConfig(
           level=logging.INFO,
           format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
           handlers=[
               logging.StreamHandler(sys.stdout)  # Docker logs to stdout
           ]
       )
   ```

3. **Enhanced docker-compose with Health Checks**
   ```yaml
   services:
     api:
       healthcheck:
         test: ["CMD", "curl", "-f", "http://localhost:8000/health/ready"]
         interval: 30s
         timeout: 10s
         retries: 3
         start_period: 40s

     agent:
       healthcheck:
         test: ["CMD", "pgrep", "-f", "pa agent"]
         interval: 60s
         timeout: 10s
         retries: 3
   ```

**Acceptance Criteria:**
- [ ] `/health` returns `{"status": "alive"}` in < 100ms
- [ ] `/health/ready` validates database connection
- [ ] `/health/agent` detects agent crashes
- [ ] Docker restarts unhealthy containers automatically
- [ ] Logs visible via `docker-compose logs -f api`

#### Phase 3: PostgreSQL Support & Migrations (Day 3)

**Goal:** Add production-ready PostgreSQL support with proper migration handling.

**Deliverables:**

1. **docker-compose.prod.yml**
   ```yaml
   version: '3.8'

   services:
     db:
       image: postgres:16-alpine
       environment:
         POSTGRES_DB: personal_assistant
         POSTGRES_USER: ${DB_USER:-pauser}
         POSTGRES_PASSWORD_FILE: /run/secrets/db_password
       volumes:
         - postgres_data:/var/lib/postgresql/data
       secrets:
         - db_password
       healthcheck:
         test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-pauser}"]
         interval: 10s
         timeout: 5s
         retries: 5
       networks:
         - app_network

     migrations:
       build: .
       command: ["alembic", "upgrade", "head"]
       environment:
         - DATABASE_URL=postgresql://${DB_USER:-pauser}:${DB_PASSWORD}@db:5432/personal_assistant
       depends_on:
         db:
           condition: service_healthy
       networks:
         - app_network

     api:
       build: .
       depends_on:
         migrations:
           condition: service_completed_successfully
         db:
           condition: service_healthy
       environment:
         - DATABASE_URL=postgresql://${DB_USER:-pauser}:${DB_PASSWORD}@db:5432/personal_assistant
         - ENV=production
       ports:
         - "8000:8000"
       networks:
         - app_network

     agent:
       build: .
       depends_on:
         migrations:
           condition: service_completed_successfully
         db:
           condition: service_healthy
       environment:
         - DATABASE_URL=postgresql://${DB_USER:-pauser}:${DB_PASSWORD}@db:5432/personal_assistant
         - ENV=production
       networks:
         - app_network

   volumes:
     postgres_data:

   secrets:
     db_password:
       file: ./secrets/db_password.txt

   networks:
     app_network:
       driver: bridge
   ```

2. **Database Configuration Updates**
   ```python
   # src/models/database.py
   def get_engine(database_url: str):
       """Create SQLAlchemy engine with appropriate pooling."""
       if "postgresql" in database_url:
           return create_engine(
               database_url,
               pool_size=20,
               max_overflow=10,
               pool_recycle=3600,
               pool_pre_ping=True,
               echo=False
           )
       else:
           return create_engine(database_url)
   ```

3. **Migration Health Check Script**
   ```bash
   #!/bin/bash
   # scripts/wait-for-db.sh

   set -e

   host="$1"
   shift
   cmd="$@"

   until PGPASSWORD=$DB_PASSWORD psql -h "$host" -U "$DB_USER" -c '\q'; do
     >&2 echo "PostgreSQL is unavailable - sleeping"
     sleep 1
   done

   >&2 echo "PostgreSQL is up - executing command"
   exec $cmd
   ```

**Acceptance Criteria:**
- [ ] PostgreSQL container starts and initializes database
- [ ] Migrations run successfully on first startup
- [ ] Migrations are idempotent (safe to re-run)
- [ ] Failed migrations prevent app containers from starting
- [ ] Connection pooling configured for PostgreSQL
- [ ] SQLite still works for development

#### Phase 4: Secrets Management & OAuth (Day 3-4)

**Goal:** Implement secure secrets management and production OAuth flow.

**Deliverables:**

1. **OAuth Token Database Model**
   ```python
   # src/models/oauth_token.py
   from sqlalchemy import String, Text, DateTime, Integer
   from sqlalchemy.orm import Mapped, mapped_column
   from src.models.database import Base
   from datetime import datetime

   class OAuthToken(Base):
       """OAuth tokens stored in database for production."""
       __tablename__ = "oauth_tokens"

       id: Mapped[int] = mapped_column(Integer, primary_key=True)
       account_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
       provider: Mapped[str] = mapped_column(String(50))  # "google", "slack", "granola"
       access_token: Mapped[str] = mapped_column(String(2000))
       refresh_token: Mapped[str | None] = mapped_column(String(2000))
       expires_at: Mapped[datetime | None] = mapped_column(DateTime)
       token_data: Mapped[str | None] = mapped_column(Text)  # JSON blob for extra data
       created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
       updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
   ```

2. **Alembic Migration**
   ```bash
   alembic revision --autogenerate -m "Add oauth_tokens table for containerized auth"
   ```

3. **OAuth API Endpoints**
   ```python
   # src/api/routes/oauth.py
   from fastapi import APIRouter, HTTPException, Depends
   from sqlalchemy.orm import Session
   from src.models.database import get_db_session
   from src.models.oauth_token import OAuthToken
   from src.integrations.oauth_utils import GoogleOAuthManager

   router = APIRouter(prefix="/oauth", tags=["oauth"])

   @router.get("/initiate")
   async def initiate_oauth(
       account_id: str,
       provider: str,
       db: Session = Depends(get_db_session)
   ):
       """Generate OAuth URL for user to visit in browser."""
       if provider == "google":
           oauth = GoogleOAuthManager(account_id)
           flow = oauth._create_flow()
           auth_url, state = flow.authorization_url(
               access_type='offline',
               prompt='consent'
           )
           return {
               "oauth_url": auth_url,
               "account_id": account_id,
               "provider": provider,
               "instructions": "Visit the URL above, complete authentication, and you'll be redirected back."
           }
       else:
           raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

   @router.get("/callback")
   async def oauth_callback(
       code: str,
       state: str,
       db: Session = Depends(get_db_session)
   ):
       """Handle OAuth callback and store tokens in database."""
       # Exchange authorization code for tokens
       # (implementation depends on provider)

       # Store tokens
       token = OAuthToken(
           account_id=account_id,
           provider=provider,
           access_token=access_token,
           refresh_token=refresh_token,
           expires_at=expires_at,
           token_data=json.dumps(token_data)
       )
       db.add(token)
       db.commit()

       return {"status": "authenticated", "account_id": account_id}

   @router.get("/status/{account_id}")
   async def oauth_status(
       account_id: str,
       db: Session = Depends(get_db_session)
   ):
       """Check authentication status for an account."""
       token = db.query(OAuthToken).filter_by(account_id=account_id).first()
       if not token:
           return {"authenticated": False, "account_id": account_id}

       is_expired = token.expires_at and token.expires_at < datetime.now()
       return {
           "authenticated": True,
           "account_id": account_id,
           "provider": token.provider,
           "expires_at": token.expires_at.isoformat() if token.expires_at else None,
           "expired": is_expired
       }
   ```

4. **Update OAuth Manager to Use Database**
   ```python
   # src/integrations/oauth_utils.py
   def get_credentials(self):
       """Get credentials from database if available, else from file."""
       # Try database first (production)
       if os.getenv("ENV") == "production":
           db = next(get_db_session())
           token = db.query(OAuthToken).filter_by(
               account_id=self.account_id,
               provider="google"
           ).first()
           if token:
               return self._credentials_from_db_token(token)

       # Fallback to file-based (development)
       return self._credentials_from_file()
   ```

5. **Secrets Documentation**
   - File: `docs/DOCKER_SECRETS.md`
   - Instructions for:
     - Creating Docker secrets
     - Rotating secrets
     - Development vs production workflows
     - Cloud provider secret managers

**Acceptance Criteria:**
- [ ] OAuth tokens stored in database for production
- [ ] API endpoint `/oauth/initiate` generates auth URLs
- [ ] OAuth callback stores tokens correctly
- [ ] Agent reads tokens from database
- [ ] File-based config still works in development
- [ ] Docker secrets work in production compose file
- [ ] Documentation covers OAuth workflow

#### Phase 5: Security Hardening & Scanning (Day 4)

**Goal:** Implement security best practices and vulnerability scanning.

**Deliverables:**

1. **Non-Root User Enforcement**
   - Already in Dockerfile (Phase 1)
   - Validation script to ensure no containers run as root

2. **Security Scanning Integration**
   ```yaml
   # .github/workflows/docker-security.yml
   name: Docker Security Scan

   on:
     push:
       branches: [main]
     pull_request:
       branches: [main]

   jobs:
     scan:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4

         - name: Build image
           run: docker build -t personal-assistant:${{ github.sha }} .

         - name: Run Trivy vulnerability scanner
           uses: aquasecurity/trivy-action@master
           with:
             image-ref: personal-assistant:${{ github.sha }}
             format: 'sarif'
             output: 'trivy-results.sarif'
             severity: 'HIGH,CRITICAL'

         - name: Upload Trivy results to GitHub Security
           uses: github/codeql-action/upload-sarif@v3
           with:
             sarif_file: 'trivy-results.sarif'

         - name: Fail on critical vulnerabilities
           uses: aquasecurity/trivy-action@master
           with:
             image-ref: personal-assistant:${{ github.sha }}
             exit-code: '1'
             severity: 'CRITICAL'
   ```

3. **Read-Only Filesystem Configuration**
   ```yaml
   # docker-compose.prod.yml
   services:
     api:
       read_only: true
       tmpfs:
         - /tmp
         - /run
       volumes:
         - app_data:/app/data  # Writable volume for database
   ```

4. **Security Checklist Documentation**
   - File: `docs/DOCKER_SECURITY.md`
   - Covers:
     - Non-root user
     - Secrets management
     - Network isolation
     - Vulnerability scanning
     - Read-only filesystem
     - Resource limits

**Acceptance Criteria:**
- [ ] All containers run as non-root user
- [ ] Trivy scan passes with no CRITICAL vulnerabilities
- [ ] Read-only filesystem works (writable volumes for data)
- [ ] Network isolation configured (api exposed, agent internal)
- [ ] Resource limits defined (CPU, memory)
- [ ] Security documentation complete

#### Phase 6: Platform Feature Detection & Fallbacks (Day 5)

**Goal:** Gracefully handle platform-specific features in containers.

**Deliverables:**

1. **Platform Detection Module**
   - File: `src/utils/platform.py`
   - Functions: `is_containerized()`, `can_use_native_notifications()`, etc.

2. **Notification Service Updates**
   - File: `src/services/notification_service.py`
   - Implement fallback to Rich terminal notifications

3. **Configuration Validation**
   ```python
   # src/utils/config.py
   def validate_config_for_environment(config: Config) -> list[str]:
       """Validate configuration for current environment."""
       warnings = []

       if is_containerized():
           if config.voice.enabled:
               warnings.append("Voice input not available in containers (no microphone access)")

           if config.notifications.sound:
               warnings.append("Sound notifications not available in containers")

       return warnings
   ```

4. **Feature Matrix Documentation**
   - File: `docs/FEATURE_AVAILABILITY.md`
   - Table showing which features work in different environments

**Acceptance Criteria:**
- [ ] Container detects it's in Docker (checks `/.dockerenv`)
- [ ] Native macOS notifications disabled in containers
- [ ] Terminal notifications work as fallback
- [ ] Menu bar app doesn't try to start in containers
- [ ] Voice input gracefully disabled or proxied
- [ ] Documentation lists feature availability

#### Phase 7: Documentation & Testing (Day 5)

**Goal:** Comprehensive documentation and automated testing.

**Deliverables:**

1. **README Updates**
   - Section: "Docker Deployment"
   - Quick start: `docker-compose up`
   - Production deployment guide

2. **Deployment Documentation**
   - File: `docs/DOCKER_DEPLOYMENT.md`
   - Covers:
     - Local development setup
     - Production deployment (AWS/GCP/Azure examples)
     - Troubleshooting common issues
     - Backup and recovery
     - Scaling strategies

3. **Docker Compose Test Suite**
   ```yaml
   # docker-compose.test.yml
   version: '3.8'

   services:
     test:
       build:
         context: .
         target: builder
       command: ["pytest", "tests/", "-v", "--cov=src"]
       environment:
         - DATABASE_URL=sqlite:////tmp/test.db
       volumes:
         - ./tests:/app/tests
         - ./src:/app/src
   ```

4. **Integration Tests for Docker**
   ```python
   # tests/integration/test_docker_health.py
   import requests
   import pytest

   @pytest.mark.integration
   def test_api_health_check():
       """Test that API health check works in Docker."""
       response = requests.get("http://localhost:8000/health")
       assert response.status_code == 200
       assert response.json()["status"] == "alive"

   @pytest.mark.integration
   def test_database_connectivity():
       """Test database connection through health check."""
       response = requests.get("http://localhost:8000/health/ready")
       assert response.status_code == 200
       assert response.json()["database"] == "connected"
   ```

**Acceptance Criteria:**
- [ ] README has Docker quick start section
- [ ] Deployment docs cover local dev and production
- [ ] Troubleshooting guide for common Docker issues
- [ ] Integration tests pass in Docker environment
- [ ] Test suite runs via `docker-compose -f docker-compose.test.yml up`

---

## Alternative Approaches Considered

### Alternative 1: Single Container with Supervisord

**Approach:** Run both API and agent in same container using supervisord process manager.

**Pros:**
- Simpler deployment (fewer containers)
- Shared filesystem (no need for network database access)
- Lower resource overhead

**Cons:**
- Violates "one process per container" principle
- Agent crash could affect API server
- More complex health checks
- Harder to scale components independently
- supervisord adds dependency and complexity

**Decision:** Rejected in favor of multi-container architecture for better isolation and scalability.

### Alternative 2: OAuth Tokens in External Secret Manager

**Approach:** Store all OAuth tokens in AWS Secrets Manager / Google Secret Manager instead of database.

**Pros:**
- Centralized secret management
- Better security (encrypted, audited)
- Automatic rotation support
- No database schema changes

**Cons:**
- External dependency (cloud provider lock-in)
- Additional API calls for every token access
- More complex local development
- Costs money (Secrets Manager pricing)

**Decision:** Hybrid approach - database for production (simple, free), with option to integrate external secret manager later.

### Alternative 3: Kubernetes-Native Deployment

**Approach:** Skip Docker Compose, go directly to Kubernetes manifests with Helm charts.

**Pros:**
- Production-grade orchestration
- Built-in scaling, load balancing, secrets
- Better for multi-node clusters

**Cons:**
- Much higher complexity
- Overkill for single-user application
- Harder local development
- Steeper learning curve

**Decision:** Start with Docker Compose (simpler), provide Kubernetes examples as optional advanced deployment.

### Alternative 4: Entrypoint Script Migration

**Approach:** Run Alembic migrations in container entrypoint script before starting app.

**Pros:**
- Simpler deployment (no separate migration container)
- Automatic migration on container start

**Cons:**
- Race conditions with multiple containers
- Failed migrations leave container in bad state
- Couples application lifecycle with migrations
- Can't rollback without redeployment

**Decision:** Use dedicated migration service with `depends_on` for safer, more predictable behavior.

---

## Acceptance Criteria

### Functional Requirements

- [ ] **Local Development**
  - [ ] `docker-compose up` starts all services in < 60 seconds
  - [ ] API accessible at `http://localhost:8000`
  - [ ] SQLite database persists across container restarts
  - [ ] CLI commands work: `docker-compose exec api pa tasks list`
  - [ ] Code changes rebuild in < 30 seconds

- [ ] **Production Deployment**
  - [ ] `docker-compose -f docker-compose.prod.yml up` starts production stack
  - [ ] PostgreSQL database initializes and runs migrations
  - [ ] OAuth tokens stored in database and persist across restarts
  - [ ] API and agent run in separate containers
  - [ ] Health checks validate system health

- [ ] **OAuth Authentication**
  - [ ] `/oauth/initiate` generates valid OAuth URL
  - [ ] OAuth callback stores tokens in database
  - [ ] Agent successfully uses tokens from database
  - [ ] Token refresh writes updated tokens back to database

- [ ] **Database Operations**
  - [ ] SQLite works in development (volume-mounted)
  - [ ] PostgreSQL works in production (connection pooling configured)
  - [ ] Migrations run before application starts
  - [ ] Failed migrations prevent app containers from starting

- [ ] **Agent Operation**
  - [ ] Agent runs in background and polls integrations
  - [ ] Agent logs activity to database
  - [ ] Agent crash doesn't affect API server
  - [ ] `/health/agent` detects agent issues

### Non-Functional Requirements

- [ ] **Performance**
  - [ ] API response time < 100ms for simple requests
  - [ ] Health check response < 50ms
  - [ ] Container startup time < 10 seconds
  - [ ] Image size < 200MB for production

- [ ] **Security**
  - [ ] No CRITICAL vulnerabilities in Trivy scan
  - [ ] Containers run as non-root user
  - [ ] Secrets not exposed in `docker inspect`
  - [ ] Read-only filesystem (except data volumes)
  - [ ] Network isolation (agent not externally accessible)

- [ ] **Reliability**
  - [ ] Failed containers restart automatically
  - [ ] Health checks detect failures within 30 seconds
  - [ ] Database connection pooling prevents exhaustion
  - [ ] Graceful shutdown on SIGTERM

- [ ] **Maintainability**
  - [ ] Clear logging to stdout/stderr
  - [ ] Documentation covers common issues
  - [ ] Configuration via environment variables
  - [ ] Easy to add new secrets

### Quality Gates

- [ ] **Testing**
  - [ ] All existing tests pass in Docker
  - [ ] Integration tests for Docker environment
  - [ ] Health check endpoints have tests
  - [ ] OAuth flow has integration tests

- [ ] **Documentation**
  - [ ] README updated with Docker instructions
  - [ ] Deployment guide complete
  - [ ] Troubleshooting guide with common errors
  - [ ] Security checklist documented

- [ ] **Code Review**
  - [ ] Dockerfile follows best practices
  - [ ] docker-compose files are well-structured
  - [ ] No hardcoded secrets in code
  - [ ] Platform detection implemented correctly

---

## Success Metrics

### Quantitative Metrics

| Metric | Current (Local) | Target (Docker) | Measurement |
|--------|----------------|-----------------|-------------|
| Setup time | 30 minutes | < 5 minutes | Time from clone to running app |
| Image size | N/A | < 200MB | `docker images` output |
| Build time | N/A | < 3 minutes | `docker build .` duration |
| Rebuild time | N/A | < 30 seconds | Code change → running container |
| Startup time | < 5 seconds | < 10 seconds | Container start → health check pass |
| API latency | 50ms | < 100ms | `/health` response time |
| Vulnerability count | N/A | 0 CRITICAL | Trivy scan results |

### Qualitative Metrics

- **Developer Experience:** Can new developers run the app with just `docker-compose up`?
- **Production Readiness:** Can the app be deployed to cloud with confidence?
- **Security Posture:** Are secrets managed securely? Are containers hardened?
- **Operational Simplicity:** Can non-technical operators manage deployments?
- **Documentation Quality:** Can someone follow the docs without getting stuck?

---

## Dependencies & Prerequisites

### External Dependencies

**Required:**
- Docker Engine >= 20.10 (for BuildKit, multi-stage builds)
- Docker Compose >= 2.0 (for depends_on conditions, health checks)
- PostgreSQL 16 (for production deployments)

**Optional:**
- Trivy (for vulnerability scanning)
- AWS CLI / gcloud / az CLI (for cloud deployments)
- kubectl + Helm (for Kubernetes deployments)

### Internal Dependencies

**Code Changes Required:**
1. Health check endpoints (new)
2. OAuth token database model (new)
3. OAuth API endpoints (new)
4. Platform detection module (new)
5. Database configuration updates (existing)
6. Secrets loading utilities (new)

**Database Changes:**
1. New table: `oauth_tokens`
2. Migration: `alembic revision --autogenerate -m "Add oauth_tokens"`

### Configuration Changes

**New Files:**
- `Dockerfile` (multi-stage)
- `docker-compose.yml` (development)
- `docker-compose.prod.yml` (production)
- `.dockerignore`
- `.env.example`
- `entrypoint.sh` (optional, for migrations)

**Modified Files:**
- `README.md` (add Docker section)
- `src/models/database.py` (add connection pooling)
- `src/utils/config.py` (add secret loading)
- `src/services/notification_service.py` (add fallbacks)

---

## Risk Analysis & Mitigation

### High-Risk Areas

#### Risk 1: OAuth Token Migration Breaking Existing Workflows

**Risk:** Users who manually edited `config.yaml` with OAuth tokens will lose access when switching to database-backed tokens.

**Likelihood:** High
**Impact:** High (blocks users from using integrations)

**Mitigation Strategy:**
1. **Migration Script:** Create `pa migrate-tokens-to-db` command to import tokens from config file
2. **Backwards Compatibility:** Support both file-based and database tokens during transition period
3. **Documentation:** Clear upgrade guide explaining the change
4. **Validation:** Warning if tokens exist in config but not in database

**Rollback Plan:** Keep file-based token loading as fallback for 2-3 releases.

#### Risk 2: Database Migration Failures in Production

**Risk:** Failed Alembic migration leaves database in inconsistent state, blocking deployments.

**Likelihood:** Medium
**Impact:** Critical (production downtime)

**Mitigation Strategy:**
1. **Dry Run:** Test migrations on production-like data in staging
2. **Idempotency:** Ensure migrations can be safely re-run
3. **Monitoring:** Alert on migration failures immediately
4. **Rollback Procedure:** Document manual rollback steps (`alembic downgrade`)
5. **Pre-deployment Check:** Validate current database state before running migrations

**Rollback Plan:**
```bash
# If migration fails midway:
docker-compose exec migrations alembic downgrade -1
# Fix migration script
# Re-deploy
```

#### Risk 3: Agent Singleton Violations

**Risk:** Multiple agent containers start simultaneously and create duplicate tasks.

**Likelihood:** Low (docker-compose enforces replicas: 1)
**Impact:** Medium (duplicate tasks, user annoyance)

**Mitigation Strategy:**
1. **Enforcement:** Use `deploy.replicas: 1` in compose file
2. **Detection:** Add database constraint on task uniqueness (email message ID)
3. **Idempotency:** Agent polling logic checks for existing tasks before creating
4. **Monitoring:** Alert if duplicate tasks detected

**Rollback Plan:** Deduplication script to merge duplicate tasks.

#### Risk 4: Secrets Exposure in Logs or Configs

**Risk:** API keys or OAuth tokens accidentally logged or committed to Git.

**Likelihood:** Medium
**Impact:** Critical (security breach)

**Mitigation Strategy:**
1. **Git Hooks:** Pre-commit hook to scan for secrets (use `gitleaks` or `detect-secrets`)
2. **Log Filtering:** Sanitize logs to redact secrets
3. **Docker Secrets:** Use secrets instead of environment variables in production
4. **Documentation:** Security guidelines for developers

**Rollback Plan:** Rotate all exposed credentials immediately.

### Medium-Risk Areas

#### Risk 5: Volume Permission Issues

**Risk:** Non-root container user can't write to volume-mounted directories.

**Likelihood:** Medium
**Impact:** Medium (container fails to start)

**Mitigation:** Set proper ownership in Dockerfile: `chown -R appuser:appuser /app/data`

#### Risk 6: Health Check False Positives

**Risk:** Health check passes but application is actually unhealthy (e.g., database is down but `/health` returns 200).

**Likelihood:** Low
**Impact:** Medium (containers not restarted when they should be)

**Mitigation:** Use `/health/ready` for deeper checks, separate liveness and readiness probes.

#### Risk 7: Image Size Bloat

**Risk:** Final image exceeds 500MB due to unnecessary dependencies.

**Likelihood:** Low
**Impact:** Low (slower deployments, higher costs)

**Mitigation:** Multi-stage builds, `.dockerignore`, remove dev dependencies.

---

## Resource Requirements

### Development Environment

**Hardware:**
- CPU: 2+ cores
- RAM: 4GB minimum, 8GB recommended
- Disk: 10GB free space (Docker images + volumes)

**Software:**
- macOS / Linux / Windows with WSL2
- Docker Desktop or Docker Engine
- Git
- Code editor (VS Code recommended)

**Time Investment:**
- Initial setup: 30-60 minutes
- Learning curve: 2-4 hours (if new to Docker)

### Production Environment

**Compute Resources (Recommended):**

| Component | CPU | Memory | Disk | Notes |
|-----------|-----|--------|------|-------|
| API Server | 0.5 cores | 512MB | - | Can scale horizontally |
| Agent | 0.25 cores | 256MB | - | Singleton only |
| PostgreSQL | 0.5 cores | 512MB | 10GB | Can use managed service |
| **Total** | **1.25 cores** | **1.25GB** | **10GB** | Single-user deployment |

**Scaling (Optional):**
- 2-4 API replicas behind load balancer: +1 core, +1GB RAM
- Redis for distributed locking (multi-agent): +0.5 core, +256MB RAM

**Cloud Provider Examples:**

| Provider | Instance Type | Monthly Cost (est.) |
|----------|--------------|---------------------|
| AWS | t3.small | $15-20 |
| GCP | e2-small | $12-18 |
| Azure | B1s | $10-15 |
| DigitalOcean | Droplet 2GB | $12 |

---

## Future Considerations

### Phase 8: Kubernetes Support (Optional)

**Goal:** Provide Kubernetes manifests for cloud-native deployments.

**Deliverables:**
- `k8s/deployment.yaml` - API and agent deployments
- `k8s/service.yaml` - Load balancer for API
- `k8s/postgres.yaml` - StatefulSet for database
- `k8s/ingress.yaml` - HTTPS ingress with cert-manager
- Helm chart for easy installation

**Benefits:**
- Horizontal scaling with pod autoscaling
- Built-in load balancing
- Rolling updates with zero downtime
- Better secrets management (k8s secrets)

### Phase 9: CI/CD Pipeline

**Goal:** Automated build, test, and deployment pipeline.

**Components:**
- GitHub Actions: Build and test on every PR
- Trivy: Vulnerability scanning before merge
- Docker Hub / ECR: Automated image publishing with version tags
- ArgoCD / Flux: GitOps-based deployments

### Phase 10: Observability Stack

**Goal:** Comprehensive monitoring, logging, and tracing.

**Components:**
- **Prometheus:** Metrics collection from health endpoints
- **Grafana:** Dashboards for API latency, task counts, agent activity
- **Loki:** Centralized log aggregation
- **Jaeger:** Distributed tracing for API requests

**Custom Metrics to Export:**
```python
# src/api/main.py
from prometheus_client import Counter, Histogram

api_requests = Counter('api_requests_total', 'Total API requests')
api_latency = Histogram('api_request_duration_seconds', 'API request latency')
tasks_created = Counter('tasks_created_total', 'Total tasks created')
```

### Phase 11: Multi-Tenancy Support

**Goal:** Support multiple users/teams with isolated data.

**Changes:**
- Add `tenant_id` to all database tables
- Row-level security in PostgreSQL
- Separate agent instances per tenant
- JWT-based authentication for API

### Phase 12: Backup and Disaster Recovery

**Goal:** Automated backups with point-in-time recovery.

**Implementation:**
- Automated PostgreSQL backups to S3/GCS
- Daily full backups + continuous WAL archiving
- Restore procedures documented and tested
- Backup encryption with KMS

---

## Documentation Plan

### New Documentation

**User-Facing:**
1. `README.md` - Update with Docker quick start
2. `docs/DOCKER_DEPLOYMENT.md` - Comprehensive deployment guide
3. `docs/DOCKER_TROUBLESHOOTING.md` - Common issues and solutions
4. `docs/FEATURE_AVAILABILITY.md` - Platform compatibility matrix

**Developer-Facing:**
5. `docs/DOCKER_DEVELOPMENT.md` - Local development with Docker
6. `docs/DOCKER_SECURITY.md` - Security best practices
7. `docs/DOCKER_SECRETS.md` - Secrets management guide
8. `docs/ARCHITECTURE_DOCKER.md` - Docker-specific architecture decisions

**Operational:**
9. `docs/DEPLOYMENT_AWS.md` - AWS ECS deployment example
10. `docs/DEPLOYMENT_GCP.md` - Google Cloud Run example
11. `docs/BACKUP_RECOVERY.md` - Database backup procedures

### Updated Documentation

**Existing Files to Update:**
- `README.md` - Add Docker installation and quick start section
- `docs/ARCHITECTURE.md` - Add containerization architecture section
- `CLAUDE.md` - Update deployment guidelines for Docker
- `.github/CONTRIBUTING.md` - Add Docker development workflow

### Documentation Structure

```
docs/
├── DOCKER_DEPLOYMENT.md          # Main deployment guide (START HERE)
│   ├── Local Development
│   ├── Production Deployment
│   ├── Cloud Provider Examples
│   └── Migration from Local to Docker
├── DOCKER_DEVELOPMENT.md         # Developer guide
│   ├── Setting up Docker locally
│   ├── Volume mounts for live reload
│   ├── Debugging in containers
│   └── Running tests in Docker
├── DOCKER_SECURITY.md            # Security hardening
│   ├── Non-root user configuration
│   ├── Secrets management
│   ├── Network isolation
│   ├── Vulnerability scanning
│   └── Security checklist
├── DOCKER_TROUBLESHOOTING.md     # Common issues
│   ├── Container won't start
│   ├── Health checks failing
│   ├── Database connection errors
│   ├── OAuth authentication problems
│   └── Permission errors
├── DOCKER_SECRETS.md             # Secrets guide
│   ├── Development (.env files)
│   ├── Production (Docker Secrets)
│   ├── Cloud providers (AWS/GCP/Azure)
│   └── OAuth token management
└── FEATURE_AVAILABILITY.md       # Platform matrix
```

---

## References & Research

### Internal References

- **Architecture Decisions:** `docs/ARCHITECTURE.md` - Layered architecture, service separation
- **Security Review:** `docs/solutions/security-issues/csv-injection-and-validation-comprehensive-fixes-document-links.md` - Security patterns
- **Configuration System:** `src/utils/config.py` - Pydantic config, environment variables
- **Database Schema:** `src/models/` - SQLAlchemy models
- **Integrations:** `src/integrations/oauth_utils.py` - OAuth flows

### External References

**FastAPI Deployment:**
- [FastAPI Official Docker Guide](https://fastapi.tiangolo.com/deployment/docker/)
- [FastAPI Production Deployment Best Practices](https://betterstack.com/community/guides/scaling-python/fastapi-docker-best-practices/)

**Docker Best Practices:**
- [Docker Best Practices for Python](https://testdriven.io/blog/docker-best-practices/)
- [Multi-Stage Builds for Python](https://pythonspeed.com/articles/multi-stage-docker-python/)
- [Docker Security Best Practices (2026)](https://oneuptime.com/blog/post/2026-01-16-docker-run-non-root-user/view)

**Database & Migrations:**
- [SQLAlchemy Connection Pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html)
- [Alembic Migrations in Docker](https://pythonspeed.com/articles/schema-migrations-server-startup/)
- [PostgreSQL Docker Best Practices](https://www.postgresql.org/docs/current/docker.html)

**Secrets Management:**
- [Docker Secrets Management (2026)](https://oneuptime.com/blog/post/2026-01-30-docker-secrets-management/view)
- [Handling Secrets in Docker](https://blog.gitguardian.com/how-to-handle-secrets-in-docker/)

**Health Checks & Monitoring:**
- [Docker Health Checks Guide (2026)](https://oneuptime.com/blog/post/2026-01-23-docker-health-checks-effectively/view)
- [FastAPI Health Check Patterns](https://medium.com/@ntjegadeesh/implementing-health-checks-and-auto-restarts-for-fastapi-applications-using-docker-and-4245aab27ece)

**Security Scanning:**
- [Trivy Vulnerability Scanning](https://trivy.dev/)
- [Scanning Docker Images (2026)](https://oneuptime.com/blog/post/2026-01-16-docker-scan-images-trivy/view)

---

## Appendix

### Appendix A: File Checklist

**New Files to Create:**

```
✓ Dockerfile
✓ docker-compose.yml
✓ docker-compose.prod.yml
✓ docker-compose.test.yml
✓ .dockerignore
✓ .env.example
✓ entrypoint.sh (optional)
✓ scripts/wait-for-db.sh
✓ src/api/routes/health.py
✓ src/api/routes/oauth.py
✓ src/models/oauth_token.py
✓ src/utils/platform.py
✓ src/utils/secrets.py
✓ tests/integration/test_docker_health.py
✓ docs/DOCKER_DEPLOYMENT.md
✓ docs/DOCKER_SECURITY.md
✓ docs/DOCKER_TROUBLESHOOTING.md
✓ docs/FEATURE_AVAILABILITY.md
✓ .github/workflows/docker-security.yml
```

### Appendix B: Environment Variables

**Complete Environment Variable Reference:**

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname
DB_USER=pauser
DB_PASSWORD=<from secrets>

# LLM Configuration
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4

# Agent Configuration
AGENT_POLL_INTERVAL=15
AGENT_AUTONOMY_LEVEL=suggest

# Environment
ENV=production  # or development, staging

# Secrets (file paths for Docker Secrets)
LLM_API_KEY_FILE=/run/secrets/llm_api_key
DB_PASSWORD_FILE=/run/secrets/db_password

# Optional: Cloud Provider
AWS_REGION=us-east-1
GCP_PROJECT_ID=my-project
```

### Appendix C: Docker Commands Quick Reference

```bash
# Development
docker-compose up                    # Start all services
docker-compose down                  # Stop all services
docker-compose logs -f api           # Follow API logs
docker-compose exec api pa tasks list  # Run CLI command
docker-compose exec api bash         # Interactive shell

# Production
docker-compose -f docker-compose.prod.yml up -d  # Start in background
docker-compose -f docker-compose.prod.yml ps     # Check status
docker-compose -f docker-compose.prod.yml logs agent  # Agent logs

# Building
docker build -t personal-assistant:latest .
docker build --no-cache .            # Force rebuild
docker images                        # List images
docker system prune -a               # Clean up

# Debugging
docker inspect personal-assistant-api-1  # Inspect container
docker stats                         # Resource usage
docker-compose exec db psql -U pauser personal_assistant  # Database access

# Security Scanning
trivy image personal-assistant:latest
docker scout cves personal-assistant:latest
```

### Appendix D: Troubleshooting Decision Tree

```
Container won't start
├─ Check logs: docker-compose logs <service>
├─ Permissions error?
│  └─ Verify volume ownership: docker-compose exec <service> ls -la /app/data
├─ Database connection error?
│  ├─ Check database is running: docker-compose ps db
│  ├─ Check DATABASE_URL env var: docker-compose exec api env | grep DATABASE
│  └─ Test connection: docker-compose exec api psql $DATABASE_URL
└─ Migration error?
   ├─ Check migration logs: docker-compose logs migrations
   └─ Manual migration: docker-compose exec api alembic upgrade head

Health check failing
├─ Test endpoint manually: curl http://localhost:8000/health
├─ Check dependencies (database): curl http://localhost:8000/health/ready
├─ Review health check config in docker-compose.yml
└─ Adjust timeouts if startup is slow

OAuth not working
├─ Check tokens exist: docker-compose exec api pa oauth status <account_id>
├─ Verify OAuth callback URL configured correctly
├─ Check secrets mounted: docker-compose exec api ls /run/secrets
└─ Review agent logs for token refresh errors

Agent not polling
├─ Check agent is running: docker-compose ps agent
├─ Check agent logs: docker-compose logs -f agent
├─ Verify agent health: curl http://localhost:8000/health/agent
└─ Check database connection from agent container
```

---

## Summary

This comprehensive plan transforms the Personal Assistant application into a production-ready containerized deployment. The phased approach ensures incremental progress with clear acceptance criteria at each stage.

**Key Achievements:**
- ✅ Multi-stage Docker builds for fast rebuilds and small images
- ✅ Flexible database support (SQLite for dev, PostgreSQL for production)
- ✅ Secure secrets management with layered strategies
- ✅ Production-ready OAuth flow with database-backed tokens
- ✅ Comprehensive health checks and monitoring
- ✅ Multi-container architecture for isolation and scalability
- ✅ Security hardening with non-root users and vulnerability scanning
- ✅ Platform feature detection with graceful fallbacks
- ✅ Complete documentation and troubleshooting guides

**Estimated Timeline:** 3-5 days for full implementation, with incremental deployment after each phase.

**Next Steps:** Review plan → Get approval → Begin Phase 1 implementation.
