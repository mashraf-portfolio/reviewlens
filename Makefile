.PHONY: install run run-live run-ui test lint fmt

PYTHON := python
SRC    := src

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"
	pre-commit install

run:
	cd $(SRC) && $(PYTHON) -m run_pipeline --fixture

run-live:
	cd $(SRC) && $(PYTHON) -m run_pipeline

run-ui:
	$(PYTHON) -m streamlit run app/streamlit_app.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check $(SRC) tests

fmt:
	$(PYTHON) -m ruff format $(SRC) tests
