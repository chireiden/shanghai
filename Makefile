
.install-deps: dev-requirements.txt
	pip install -U -r dev-requirements.txt
	touch .install-deps

flake: .install-deps
	flake8 --exclude=shanghai/local.py .

.develop: .install-deps $(shell find shanghai -type f)
	pip install -e .
	touch .develop

test: flake .develop
	py.test -s -v --cov=shanghai --cov-config .coveragerc ./tests/

install:
	python -m pip install -U pip
	pip install -r dev-requirements.txt

.PHONY: all flake test vtest
