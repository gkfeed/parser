merge-to-master:
	git checkout master
	git merge dev
	git push
	git checkout dev

test:
	IS_WORKER=1 pipenv run test

dev:
	IS_WORKER=1 pipenv run app
