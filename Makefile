PYTHON = .venv/bin/python

merge-to-master:
	git checkout master
	git merge dev
	git push
	git checkout dev

test:
	IS_WORKER=1 $(PYTHON) -m pytest

dev:
	IS_WORKER=1 $(PYTHON) < app/main.py

debug:
ifdef FILE
	IS_WORKER=1 $(PYTHON) -m pytest --pdb $(FILE)
else
	IS_WORKER=1 $(PYTHON) -m pytest --pdb
endif

.PHONY: merge-to-master test dev debug

init-dev:
	uv sync --all-extras

lock-dev:
	uv pip freeze > requirements-dev.txt

lock:
	uv export --no-hashes --format requirements-txt > requirements.txt

lint:
	uvx ruff check . && uvx typos
