PYTHON = .venv/bin/python
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

dispatcher:
	$(PYTHON) -m app.run.dispatcher

worker_light: redis
	$(PYTHON) -m app.run.worker_light

worker_http: redis
	$(PYTHON) -m app.run.worker_http

worker_browser: redis
	$(PYTHON) -m app.run.worker_browser

redis:
	docker compose up -d redis

debug:
ifdef FILE
	$(PYTHON) -m pytest --pdb $(FILE)
else
	$(PYTHON) -m pytest --pdb
endif

.PHONY: merge-to-master test test-integration debug format docker-update docker-browser-start docker-browser-stop docker-restart-workers

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
	$(PRODUCTION_COMPOSE) stop
	$(PRODUCTION_COMPOSE) rm -f
	$(PRODUCTION_COMPOSE) build
	$(PRODUCTION_COMPOSE) up -d --remove-orphans

docker-browser-start:
	docker compose --profile browser pull chrome
	docker compose --profile browser up -d worker_browser

docker-browser-stop:
	docker compose --profile browser stop worker_browser chrome

docker-restart-workers:
	docker compose up -d --build --force-recreate --no-deps worker_light worker_http
