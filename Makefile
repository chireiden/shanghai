
.install-deps: requirements-dev.txt
	pip install -U -r requirements-dev.txt
	touch .install-deps

flake: .install-deps
	flake8 shanghai

.develop: .install-deps $(shell find shanghai -type f)
	pip install -e .
	touch .develop

test: flake .develop
	py.test -s -v --cov=shanghai --cov-config .coveragerc ./tests/

install:
	pip install -U pip
	pip install -U -r requirements-dev.txt

.PHONY: all flake test vtest
