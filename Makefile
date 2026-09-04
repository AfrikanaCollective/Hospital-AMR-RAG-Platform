# Hospital RAG Platform — developer entrypoints. See README.md.
COMPOSE ?= docker compose
PROFILE ?= dev
BE      ?= cd backend &&

.PHONY: help up down logs build migrate seed gen-data ingest-deid \
        prepare-guidelines fetch-guidelines test lint typecheck eval fmt

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n", $$1, $$2}'

up: ## start the dev compose stack
	$(COMPOSE) --profile $(PROFILE) up -d

down: ## stop the compose stack
	$(COMPOSE) --profile $(PROFILE) down

logs: ## tail api + worker logs
	$(COMPOSE) --profile $(PROFILE) logs -f api worker

build: ## rebuild images
	$(COMPOSE) --profile $(PROFILE) build

migrate: ## alembic upgrade head
	$(COMPOSE) --profile $(PROFILE) exec api alembic upgrade head

seed: ## create schemas/roles + seed rubric domains + demo users
	$(COMPOSE) --profile $(PROFILE) exec api python -m scripts.seed_db

gen-data: ## generate synthetic patient records (fallback); domain from RECORD_DOMAIN (default neonatal)
	$(COMPOSE) --profile $(PROFILE) exec api python -m scripts.generate_synthetic_records --count 200 --out /app/data/patient_records/synthetic

ingest-deid: ## map an attested de-identified dataset onto record.py (ARCH-039); DATASET=<dir>
	$(COMPOSE) --profile $(PROFILE) exec api python -m scripts.ingest_deidentified_records \
	  --dataset-dir /app/$(or $(DATASET),data/patient_records/deidentified/newborn_nbu_2021) --attest-deidentified

prepare-guidelines: ## validate the operator-provided guideline corpus in data/sample_guidelines/ (ARCH-038)
	$(COMPOSE) --profile $(PROFILE) exec api python -m scripts.prepare_sample_guidelines --dir /app/data/sample_guidelines

fetch-guidelines: prepare-guidelines ## deprecated alias for prepare-guidelines

test: ## backend pytest (offline; includes gating safety tests)
	$(BE) pytest -q

lint: ## ruff check + format check
	$(BE) ruff check . && ruff format --check .

fmt: ## apply ruff formatting
	$(BE) ruff format . && ruff check --fix .

typecheck: ## mypy
	$(BE) mypy app

eval: ## run the evaluation harness against the fixed synthetic test set
	$(BE) python -m app.eval.run --snapshot latest
