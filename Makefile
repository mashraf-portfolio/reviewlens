.PHONY: install run test lint fmt

PYTHON := python
SRC    := src

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"
	pre-commit install

run:
	$(PYTHON) -m streamlit run app/streamlit_app.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check $(SRC) app tests

fmt:
	$(PYTHON) -m ruff format $(SRC) app tests
