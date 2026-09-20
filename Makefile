.DEFAULT_GOAL := help
COMPOSE := docker compose

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-14s %s\n", $$1, $$2}'

up: ## Start db + redis + backend + worker + frontend
	$(COMPOSE) up -d

down: ## Stop the stack
	$(COMPOSE) down

ps: ## Stack status
	$(COMPOSE) ps

reset-db: ## Drop volumes and restart the stack
	$(COMPOSE) down -v && $(COMPOSE) up -d

dev: ## Run backend locally with reload (needs db+redis up)
	cd backend && uvicorn app.main:app --reload --port 8000

worker: ## Run the arq ingestion worker locally
	cd backend && arq app.ingestion.worker.WorkerSettings

migrate: ## Apply Alembic migrations
	cd backend && alembic upgrade head

init-db: ## Dev shortcut: create_all + indexes (no Alembic)
	cd backend && python ../scripts/init_db.py

seed: ## Rebuild fixtures data into the db (Phase 1)
	cd backend && python ../scripts/generate_novatech.py --all && python ../scripts/seed.py

seed-peers: ## Load the 3-peer benchmark fixture (Phase 6)
	cd backend && python ../scripts/seed_peers.py

eval-rag: ## Run the RAG golden-set eval (Phase 4)
	cd backend && python ../scripts/eval_rag.py

lint: ## ruff + mypy
	cd backend && ruff check . && mypy app

type: ## mypy only
	cd backend && mypy app

test: ## pytest with coverage
	cd backend && pytest -q --cov=app --cov-report=term-missing

demo: ## Print the full NovaTech DCF bridge (Phase 2)
	cd backend && python ../scripts/finmod_demo.py

.PHONY: help up down ps reset-db dev worker migrate init-db seed seed-peers eval-rag lint type test demo
