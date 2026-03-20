.PHONY: build up down logs restart shell init clean

# Build Docker image
build:
	docker compose build

# Start containers
up:
	docker compose up -d

# Start containers with logs
up-logs:
	docker compose up

# Stop containers
down:
	docker compose down

# View logs
logs:
	docker compose logs -f

# Restart containers
restart:
	docker compose restart

# Open shell in container
shell:
	docker compose exec cmdb /bin/bash

# Initialize database (if needed)
init:
	docker compose exec cmdb python -c "from app import db, app; app.app_context().push(); db.create_all(); print('Database initialized!')"

# Default target
all: build up
