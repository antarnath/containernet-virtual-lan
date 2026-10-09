.PHONY: up down build clean logs test lint help

help:
	@echo "ContainerNet — common targets:"
	@echo "  make up        # docker compose up -d --build"
	@echo "  make down      # docker compose down"
	@echo "  make build     # docker compose build"
	@echo "  make logs      # tail all container logs"
	@echo "  make test      # run the manual end-to-end tests"
	@echo "  make lint      # ruff + frontend eslint"
	@echo "  make clean     # wipe containers + networks + volumes"

up:
	docker compose up -d --build
	@echo ""
	@echo "Dashboard: http://localhost:5173"
	@echo "API:       http://localhost:8000"
	@echo "API docs:  http://localhost:8000/docs"
	@echo ""
	@echo "Click '⚡ Killer demo' on the projects page to see ARP spoof MITM live."

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f --tail=100

test:
	@echo "Running backend end-to-end tests…"
	@for t in tests/manual/test_*.py; do \
		echo ""; \
		echo "=== $$t ==="; \
		python3 $$t || exit 1; \
	done
	@echo ""
	@echo "All tests passed."

lint:
	@echo "Backend (ruff):"
	@cd backend && ruff check . || (command -v ruff >/dev/null 2>&1 || pip install ruff)
	@echo "Frontend (eslint):"
	@cd frontend && npm run lint || true

# Wipe all ContainerNet state — containers, networks, and the
# Postgres volume. The orphan sweeper will leave half-started
# projects lying around if you don't; this is the hammer for
# "I just want a clean slate".
clean:
	docker compose down -v --remove-orphans 2>&1 | tail -1
	@echo "Pruning containernet bridges + containers…"
	-docker network prune -f --filter "label=containernet.link=true" 2>&1 | tail -1
	-docker network prune -f --filter "label=containernet.project=true" 2>&1 | tail -1
	-docker container prune -f --filter "label=containernet.host=true" 2>&1 | tail -1
	-docker container prune -f --filter "label=containernet.router=true" 2>&1 | tail -1
	@echo ""
	@echo "Cleaned. Run 'make up' to start fresh."
