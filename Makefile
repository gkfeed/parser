PYTHON = .venv/bin/python
ALEMBIC = .venv/bin/alembic
PRODUCTION_COMPOSE = docker compose -f docker-compose.yml -f docker-compose.production.yml

merge-to-master:
	git checkout master
	git merge dev
	git push
	git checkout dev

test:
ifdef FILE
	$(PYTHON) -m pytest -m "not integration" $(FILE)
else
	$(PYTHON) -m pytest -m "not integration"
endif

test-integration:
ifdef FILE
	$(PYTHON) -m pytest -m integration $(FILE)
else
	$(PYTHON) -m pytest -m integration
endif

dev:
	$(PYTHON) -m app.main

dispatcher:
	$(PYTHON) -m app.run.dispatcher

worker_light: redis
	$(PYTHON) -m app.run.worker_light

worker_heavy: redis
	$(PYTHON) -m app.run.worker_heavy

redis:
	docker compose up -d redis

debug:
ifdef FILE
	$(PYTHON) -m pytest --pdb $(FILE)
else
	$(PYTHON) -m pytest --pdb
endif

.PHONY: merge-to-master test test-integration dev debug format migrate makemigrations docker-update docker-heavy-start docker-heavy-stop docker-restart-workers

migrate:
	$(ALEMBIC) upgrade head

makemigrations:
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

init-dev:
	uv sync --all-extras

lock-dev:
	uv pip freeze > requirements-dev.txt

lock:
	uv export --no-dev --no-hashes --format requirements-txt > requirements.txt

lint:
	uvx ruff check . 
	uvx typos
	uv run mypy app/
	uv run pyright app/
	uvx pyrefly check . 
	uvx ty check

format:
ifdef FILE
	uvx ruff format $(FILE)
else
	uvx ruff format .
endif

docker-update:
	git fetch && git pull
	$(PRODUCTION_COMPOSE) --profile heavy stop && $(PRODUCTION_COMPOSE) --profile heavy rm -f
	$(PRODUCTION_COMPOSE) build
	$(PRODUCTION_COMPOSE) up -d

docker-heavy-start:
	$(PRODUCTION_COMPOSE) --profile heavy up -d worker_heavy

docker-heavy-stop:
	$(PRODUCTION_COMPOSE) --profile heavy stop worker_heavy chrome

docker-restart-workers:
	docker compose up -d --build --force-recreate --no-deps worker_light worker_heavy
