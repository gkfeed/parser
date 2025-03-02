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

.PHONY: merge-to-master test dev
