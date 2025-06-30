PYTHON = .venv/bin/python

merge-to-master:
	git checkout master
	git merge dev
	git push
	git checkout dev

test:
ifdef FILE
	IS_WORKER=1 $(PYTHON) -m pytest $(FILE)
else
	IS_WORKER=1 $(PYTHON) -m pytest
endif

dev:
	IS_WORKER=1 $(PYTHON) < app/main.py

debug:
ifdef FILE
	IS_WORKER=1 $(PYTHON) -m pytest --pdb $(FILE)
else
	IS_WORKER=1 $(PYTHON) -m pytest --pdb
endif

.PHONY: merge-to-master test dev debug format

init-dev:
	uv sync --all-extras

lock-dev:
	uv pip freeze > requirements-dev.txt

lock:
	uv export --no-hashes --format requirements-txt > requirements.txt

lint:
	uvx ruff check . && uvx typos && uv run mypy app/ && uv run pyright app/

format:
ifdef FILE
	uvx ruff format $(FILE)
else
	uvx ruff format .
endif
