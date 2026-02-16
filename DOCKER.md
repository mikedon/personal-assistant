# Docker Deployment Guide

This guide covers running Personal Assistant in Docker containers for both local development and production deployment.

## Quick Start

### Development (SQLite)

```bash
# 1. Copy example config
cp config.example.yaml config.yaml

# 2. Edit config.yaml with your API keys

# 3. Start containers
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# 4. Access API at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### Production (PostgreSQL)

```bash
# 1. Set up secrets
echo -n "your-db-password" > secrets/db_password.txt
echo -n "your-llm-api-key" > secrets/llm_api_key.txt
echo -n "your-google-client-id" > secrets/google_client_id.txt
echo -n "your-google-client-secret" > secrets/google_client_secret.txt

# 2. Set DB password environment variable
export DB_PASSWORD="your-db-password"

# 3. Start containers
docker-compose up -d

# 4. Check health
docker-compose ps
curl http://localhost:8000/health
```

## Architecture

The application uses a multi-container architecture:

```
┌─────────────────┐
│   PostgreSQL    │  (Production only)
│   Database      │
└────────┬────────┘
         │
    ┌────┴────┬────────────┬──────────┐
    │         │            │          │
┌───▼───┐ ┌──▼──┐  ┌──────▼─────┐ ┌──▼─────┐
│ Migr. │ │ API │  │   Agent    │ │ OAuth  │
│ (init)│ │     │  │ (Background)│ │ Tokens │
└───────┘ └─────┘  └────────────┘ └────────┘
```

**Services:**
- **db**: PostgreSQL database (production)
- **migration**: Runs Alembic migrations once on startup
- **api**: FastAPI server handling HTTP requests
- **agent**: Background polling service (emails, Slack, etc.)

**Volumes:**
- **postgres_data**: PostgreSQL data persistence
- **oauth_tokens**: OAuth token storage (shared between API and agent)
- **sqlite_data**: SQLite database (development only)

## Configuration

### Environment Variables

**Development** (via .env or docker-compose.dev.yml):
```bash
PA_LLM_API_KEY=sk-...
PA_GOOGLE_CLIENT_ID=...
PA_GOOGLE_CLIENT_SECRET=...
PA_DATABASE_URL=sqlite:///data/tasks.db  # Auto-set in dev mode
```

**Production** (via Docker Secrets):
```bash
PA_DATABASE_URL=postgresql://pauser:password@db:5432/personal_assistant
PA_LLM_API_KEY_FILE=/run/secrets/llm_api_key
PA_GOOGLE_CLIENT_ID_FILE=/run/secrets/google_client_id
PA_GOOGLE_CLIENT_SECRET_FILE=/run/secrets/google_client_secret
```

### Secrets Management

Create secrets directory with required files:

```bash
# Create secrets directory
mkdir -p secrets

# Add secrets (no trailing newlines)
echo -n "your-secret" > secrets/db_password.txt
echo -n "your-api-key" > secrets/llm_api_key.txt
echo -n "client-id" > secrets/google_client_id.txt
echo -n "client-secret" > secrets/google_client_secret.txt

# Verify (should show NO trailing newline)
cat secrets/db_password.txt | od -c
```

**Security Best Practices:**
- Never commit secrets to Git (secrets/ is in .gitignore)
- Use environment variables for local development
- Use Docker Secrets for production deployment
- Rotate secrets regularly
- Use separate secrets for dev/staging/production

## Database Migrations

Migrations run automatically via the `migration` service on startup.

### Manual Migration Commands

```bash
# Check migration status
docker-compose exec api alembic current

# View migration history
docker-compose exec api alembic history

# Create new migration
docker-compose exec api alembic revision --autogenerate -m "Description"

# Apply migrations manually
docker-compose exec api alembic upgrade head

# Rollback migration
docker-compose exec api alembic downgrade -1
```

## Health Checks

### Endpoints

- `GET /health` - Basic health (always returns 200)
- `GET /health/ready` - Readiness check (database + config)
- `GET /health/agent` - Agent status (polling state)

### Check Health Status

```bash
# Basic health
curl http://localhost:8000/health

# Readiness (includes DB check)
curl http://localhost:8000/health/ready

# Agent status
curl http://localhost:8000/health/agent

# Docker health status
docker-compose ps
```

### Health Check Failures

If health checks fail:

```bash
# Check logs
docker-compose logs api
docker-compose logs agent
docker-compose logs db

# Restart services
docker-compose restart api
docker-compose restart agent

# Full restart
docker-compose down
docker-compose up -d
```

## Common Operations

### Starting Services

```bash
# Development (SQLite, hot-reload)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Production (PostgreSQL, optimized)
docker-compose up -d

# Start specific service
docker-compose up api
```

### Stopping Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (⚠️ deletes data)
docker-compose down -v

# Stop specific service
docker-compose stop api
```

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f agent
docker-compose logs -f db

# Last 100 lines
docker-compose logs --tail=100 api
```

### Accessing Containers

```bash
# Open shell in API container
docker-compose exec api /bin/bash

# Run CLI command
docker-compose exec api pa tasks list
docker-compose exec api pa agent status

# Access PostgreSQL
docker-compose exec db psql -U pauser -d personal_assistant
```

### Rebuilding Images

```bash
# Rebuild after code changes
docker-compose build

# Rebuild specific service
docker-compose build api

# Rebuild without cache
docker-compose build --no-cache

# Rebuild and restart
docker-compose up -d --build
```

## Development Workflow

### Local Development with Docker

```bash
# 1. Start services with hot-reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# 2. Code changes auto-reload (src/ is mounted)

# 3. Run tests
docker-compose exec api pytest

# 4. Access logs
docker-compose logs -f api

# 5. Stop when done
docker-compose down
```

### Hybrid Development (Local Code, Dockerized DB)

```bash
# Start only database
docker-compose up db -d

# Run API locally
export PA_DATABASE_URL=postgresql://pauser:changeme@localhost:5432/personal_assistant
pa server --reload

# Run agent locally
pa agent start --foreground
```

## Production Deployment

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 1.29+
- 1GB+ RAM
- 10GB+ disk space

### Deployment Steps

1. **Set up secrets:**
   ```bash
   mkdir -p secrets
   echo -n "strong-password" > secrets/db_password.txt
   echo -n "your-llm-key" > secrets/llm_api_key.txt
   echo -n "oauth-client-id" > secrets/google_client_id.txt
   echo -n "oauth-secret" > secrets/google_client_secret.txt
   ```

2. **Configure environment:**
   ```bash
   export DB_PASSWORD="strong-password"
   ```

3. **Start services:**
   ```bash
   docker-compose up -d
   ```

4. **Verify deployment:**
   ```bash
   # Check all services are running
   docker-compose ps

   # Check health endpoints
   curl http://localhost:8000/health
   curl http://localhost:8000/health/ready
   curl http://localhost:8000/health/agent

   # Check logs for errors
   docker-compose logs --tail=100
   ```

5. **Set up reverse proxy (optional):**
   ```nginx
   # Nginx configuration
   server {
       listen 80;
       server_name assistant.example.com;

       location / {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

### Production Configuration

Edit `config.yaml` for production settings:

```yaml
# Production settings
agent:
  enabled: true
  polling_interval: 300  # 5 minutes
  autonomy_level: "auto"

notifications:
  enabled: false  # Disable OS notifications in containers

llm:
  model: "gpt-4"
  temperature: 0.3
```

## Troubleshooting

### Database Connection Issues

```bash
# Check database is running
docker-compose ps db

# Check database logs
docker-compose logs db

# Test connection
docker-compose exec db psql -U pauser -d personal_assistant -c "SELECT 1;"

# Verify DATABASE_URL
docker-compose exec api env | grep PA_DATABASE_URL
```

### Migration Failures

```bash
# Check migration logs
docker-compose logs migration

# Run migrations manually
docker-compose exec api alembic upgrade head

# Reset database (⚠️ deletes data)
docker-compose down -v
docker-compose up -d
```

### Agent Not Polling

```bash
# Check agent logs
docker-compose logs -f agent

# Verify agent is running
curl http://localhost:8000/health/agent

# Check agent configuration
docker-compose exec api pa agent status

# Restart agent
docker-compose restart agent
```

### OAuth Authentication Issues

```bash
# Check OAuth tokens volume
docker volume inspect personal-assistant_oauth_tokens

# Check token file permissions
docker-compose exec api ls -la /app/data/

# Reset OAuth tokens
docker-compose down
docker volume rm personal-assistant_oauth_tokens
docker-compose up -d
```

### Container Won't Start

```bash
# Check logs for errors
docker-compose logs api

# Check resource usage
docker stats

# Verify secrets exist
ls -la secrets/

# Rebuild image
docker-compose build --no-cache api
docker-compose up -d
```

## Performance Tuning

### Resource Limits

Add resource constraints in `docker-compose.yml`:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

### Database Optimization

```bash
# PostgreSQL tuning (in docker-compose.yml)
db:
  environment:
    POSTGRES_INITDB_ARGS: "-E UTF8 --locale=C"
  command:
    - postgres
    - -c
    - shared_buffers=256MB
    - -c
    - max_connections=100
```

### Logging

Reduce log verbosity in production:

```yaml
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Security Hardening

### Non-Root User

All containers run as non-root user `appuser` (UID 1000).

### Network Isolation

Services communicate via internal Docker network `pa-network`.

### Secrets Management

Use Docker Secrets (not environment variables) for sensitive data.

### Vulnerability Scanning

```bash
# Scan images with Trivy
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image personal-assistant-api:latest

# Scan for CVEs
docker scout cves personal-assistant-api:latest
```

## Backup and Restore

### Database Backup

```bash
# Backup PostgreSQL
docker-compose exec db pg_dump -U pauser personal_assistant > backup.sql

# Backup with timestamp
docker-compose exec db pg_dump -U pauser personal_assistant > \
  "backup-$(date +%Y%m%d-%H%M%S).sql"
```

### Database Restore

```bash
# Restore PostgreSQL
docker-compose exec -T db psql -U pauser personal_assistant < backup.sql
```

### OAuth Tokens Backup

```bash
# Backup OAuth tokens volume
docker run --rm -v personal-assistant_oauth_tokens:/data \
  -v $(pwd):/backup alpine tar czf /backup/oauth-backup.tar.gz -C /data .

# Restore OAuth tokens
docker run --rm -v personal-assistant_oauth_tokens:/data \
  -v $(pwd):/backup alpine tar xzf /backup/oauth-backup.tar.gz -C /data
```

## Monitoring

### Container Metrics

```bash
# Real-time stats
docker stats

# Specific container
docker stats personal-assistant-api
```

### Application Metrics

```bash
# Task counts
docker-compose exec api pa tasks list | wc -l

# Agent activity
docker-compose exec api sqlite3 /app/data/tasks.db \
  "SELECT COUNT(*) FROM agent_logs WHERE created_at > datetime('now', '-1 day');"
```

### Alerting

Set up health check monitoring:

```bash
# Cron job for health monitoring
*/5 * * * * curl -f http://localhost:8000/health/ready || \
  echo "Personal Assistant health check failed" | mail -s "Alert" admin@example.com
```

## Upgrading

### Rolling Update

```bash
# 1. Pull latest code
git pull origin main

# 2. Rebuild images
docker-compose build

# 3. Stop old containers
docker-compose down

# 4. Start new containers
docker-compose up -d

# 5. Verify deployment
docker-compose ps
curl http://localhost:8000/health
```

### Zero-Downtime Update (Multi-Host)

Use Docker Swarm or Kubernetes for zero-downtime deployments.

## FAQ

**Q: Can I use SQLite in production?**
A: Not recommended. PostgreSQL provides better concurrency and reliability.

**Q: How do I scale the agent?**
A: Run multiple agent containers with different polling intervals or integration filters.

**Q: Can I run this on ARM (Apple Silicon/Raspberry Pi)?**
A: Yes, use `python:3.11-slim` base image which supports multi-arch.

**Q: How do I debug inside a container?**
A: Use `docker-compose exec api /bin/bash` to access shell.

**Q: What's the recommended backup frequency?**
A: Daily database backups, weekly OAuth token backups.

## Additional Resources

- [Personal Assistant Documentation](README.md)
- [Architecture Guide](docs/ARCHITECTURE.md)
- [Database Migrations](MIGRATIONS.md)
- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
