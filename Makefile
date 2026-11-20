# Pinpoint: common tasks. Run `make help` for the list.
.DEFAULT_GOAL := help
APP_ID := pinpoint
VERSION := $(shell sed -n "s:.*<version>\(.*\)</version>.*:\1:p" appinfo/info.xml | head -1)
COMPOSE := docker compose -f dev/docker-compose.yml
PY ?= .venv/bin/python

.PHONY: help
help: ## Show this help
	@grep -E "^[a-z-]+:.*## " $(MAKEFILE_LIST) | awk -F ":.*## " "{printf \"  %-16s %s\\n\", \$$1, \$$2}"

.PHONY: venv
venv: ## Create .venv with the development dependencies
	uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt

.PHONY: frontend
frontend: ## Build the frontend into ex_app/js
	npm ci && npm run build

.PHONY: dev-up
dev-up: ## Start Nextcloud and Pinpoint locally and register the ExApp (LLM_URL, LLM_MODEL to change the model)
	$(COMPOSE) up -d --build --wait
	dev/setup.sh

.PHONY: dev-down
dev-down: ## Stop the local stack (keeps its data)
	$(COMPOSE) down

.PHONY: dev-logs
dev-logs: ## Follow the ExApp logs
	$(COMPOSE) logs -f pinpoint

.PHONY: lint
lint: ## Lint and type-check Python and the frontend
	$(PY) -m ruff check ex_app tests evals dev
	$(PY) -m ruff format --check ex_app tests evals dev
	$(PY) -m mypy
	npm run typecheck

.PHONY: test
test: ## Unit and API tests
	$(PY) -m pytest

.PHONY: test-integration
test-integration: ## Integration tests against the local stack with the mock model
	$(COMPOSE) -f tests/integration/docker-compose.ci.yml up -d --build --wait
	LLM_URL=http://mockllm:8000/v1 LLM_MODEL=mock-model dev/setup.sh
	$(PY) -m pytest -m integration tests/integration

.PHONY: eval
eval: ## Verification-layer eval with injected faults (what CI runs)
	$(PY) evals/run.py oracle --check --report evals/results/oracle.md

.PHONY: eval-model
eval-model: ## Full pipeline with a real model: make eval-model LLM_URL=http://localhost:11434/v1 LLM_MODEL=qwen2.5:7b
	$(PY) evals/run.py openai --base-url $(LLM_URL) --model $(LLM_MODEL) --report evals/results/$(subst :,-,$(LLM_MODEL)).md

.PHONY: screenshots
screenshots: ## Retake README screenshots from the local stack (needs Google Chrome)
	node scripts/screenshots.mjs

.PHONY: appstore
appstore: ## Package build/appstore/pinpoint.tar.gz for the App Store
	rm -rf build/appstore && mkdir -p build/appstore/$(APP_ID)
	cp -r appinfo img LICENSE README.md CHANGELOG.md build/appstore/$(APP_ID)/
	tar -czf build/appstore/$(APP_ID).tar.gz -C build/appstore $(APP_ID)
	@echo "build/appstore/$(APP_ID).tar.gz ($(VERSION))"

.PHONY: sign
sign: appstore ## Print the release signature (needs ~/.nextcloud/certificates/pinpoint.key)
	openssl dgst -sha512 -sign ~/.nextcloud/certificates/$(APP_ID).key build/appstore/$(APP_ID).tar.gz | openssl base64 -A; echo
