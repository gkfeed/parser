PYTHON = .venv/bin/python
ALEMBIC = .venv/bin/alembic

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

.PHONY: merge-to-master test test-integration dev debug format migrate makemigrations docker-restart-workers

migrate:
	$(ALEMBIC) upgrade head

makemigrations:
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

init-dev:
	uv sync --all-extras

lock-dev:
	uv pip freeze > requirements-dev.txt

lock:
	uv export --no-hashes --format requirements-txt > requirements.txt

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
	docker compose stop && docker compose rm -f
	docker compose build
	docker compose up -d

docker-restart-workers:
	docker compose up -d --build --force-recreate --no-deps worker_light worker_heavy
