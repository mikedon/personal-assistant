# Personal Assistant - Docker Management Makefile

.PHONY: help dev prod build up down logs shell test clean secrets

help: ## Show this help message
	@echo "Personal Assistant - Docker Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Development
dev: ## Start development environment (SQLite, hot-reload)
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

dev-build: ## Rebuild and start development environment
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build

dev-down: ## Stop development environment
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml down

# Production
prod: secrets ## Start production environment (PostgreSQL)
	docker-compose up -d

prod-build: secrets ## Rebuild and start production environment
	docker-compose up -d --build

prod-down: ## Stop production environment
	docker-compose down

# Building
build: ## Build all images
	docker-compose build

build-no-cache: ## Build all images without cache
	docker-compose build --no-cache

# Container Management
up: ## Start all services
	docker-compose up -d

down: ## Stop all services
	docker-compose down

restart: ## Restart all services
	docker-compose restart

# Logs
logs: ## View logs (all services)
	docker-compose logs -f

logs-api: ## View API logs
	docker-compose logs -f api

logs-agent: ## View agent logs
	docker-compose logs -f agent

logs-db: ## View database logs
	docker-compose logs -f db

# Shell Access
shell: ## Open shell in API container
	docker-compose exec api /bin/bash

shell-db: ## Open PostgreSQL shell
	docker-compose exec db psql -U pauser -d personal_assistant

# Testing
test: ## Run tests in container
	docker-compose exec api pytest

test-cov: ## Run tests with coverage
	docker-compose exec api pytest --cov=src --cov-report=html

lint: ## Run linters
	docker-compose exec api ruff check src/ tests/
	docker-compose exec api ruff format --check src/ tests/

# Health Checks
health: ## Check service health
	@echo "Basic health:"
	@curl -s http://localhost:8000/health | jq .
	@echo "\nReadiness check:"
	@curl -s http://localhost:8000/health/ready | jq .
	@echo "\nAgent status:"
	@curl -s http://localhost:8000/health/agent | jq .

status: ## Show container status
	docker-compose ps

# Database
db-migrate: ## Run database migrations
	docker-compose exec api alembic upgrade head

db-rollback: ## Rollback last migration
	docker-compose exec api alembic downgrade -1

db-history: ## Show migration history
	docker-compose exec api alembic history

db-current: ## Show current migration
	docker-compose exec api alembic current

db-backup: ## Backup PostgreSQL database
	docker-compose exec db pg_dump -U pauser personal_assistant > backup-$(shell date +%Y%m%d-%H%M%S).sql

# Cleanup
clean: ## Remove all containers and volumes (⚠️ deletes data)
	docker-compose down -v

clean-images: ## Remove built images
	docker rmi personal-assistant-api personal-assistant-agent 2>/dev/null || true

prune: ## Remove unused Docker resources
	docker system prune -f

# Secrets Setup
secrets: ## Create secrets directory and example files
	@mkdir -p secrets
	@if [ ! -f secrets/db_password.txt ]; then \
		echo "Creating secrets/db_password.txt.example"; \
		echo -n "changeme" > secrets/db_password.txt.example; \
	fi
	@if [ ! -f secrets/llm_api_key.txt ]; then \
		echo "⚠️  Warning: secrets/llm_api_key.txt not found"; \
		echo "   Copy secrets/llm_api_key.txt.example and add your API key"; \
	fi
	@if [ ! -f secrets/google_client_id.txt ]; then \
		echo "⚠️  Warning: secrets/google_client_id.txt not found"; \
		echo "   Copy secrets/google_client_id.txt.example and add your client ID"; \
	fi
	@if [ ! -f secrets/google_client_secret.txt ]; then \
		echo "⚠️  Warning: secrets/google_client_secret.txt not found"; \
		echo "   Copy secrets/google_client_secret.txt.example and add your client secret"; \
	fi

# Quick Start
quickstart: ## Quick start guide
	@echo "Personal Assistant - Quick Start"
	@echo ""
	@echo "1. Development (SQLite):"
	@echo "   make dev"
	@echo ""
	@echo "2. Production (PostgreSQL):"
	@echo "   make secrets"
	@echo "   cp secrets/*.example secrets/*.txt"
	@echo "   # Edit secrets/*.txt files"
	@echo "   export DB_PASSWORD='your-password'"
	@echo "   make prod"
	@echo ""
	@echo "3. Access:"
	@echo "   API: http://localhost:8000"
	@echo "   Docs: http://localhost:8000/docs"
	@echo ""
	@echo "4. Commands:"
	@echo "   make help      - Show all commands"
	@echo "   make logs      - View logs"
	@echo "   make health    - Check health"
	@echo "   make shell     - Open shell"
