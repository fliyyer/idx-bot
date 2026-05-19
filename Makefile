SHELL := /bin/bash

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help setup install run run-no-discord clean

help:
	@echo "Available commands:"
	@echo "  make setup           Create venv + install dependencies"
	@echo "  make install         Install dependencies into existing venv"
	@echo "  make run             Run stock bot with variables from .env"
	@echo "  make run-no-discord  Run bot without sending to Discord"
	@echo "  make clean           Remove venv and cache"

setup:
	python3 -m venv $(VENV) || \
	( \
		echo "python3-venv tidak tersedia, fallback ke virtualenv (user-level)..." && \
		python3 -m pip install --user virtualenv && \
		python3 -m virtualenv $(VENV) \
	)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install:
	$(PIP) install -r requirements.txt

run:
	set -a; source .env; set +a; \
	$(PYTHON) main.py

run-no-discord:
	set -a; source .env; set +a; \
	DISCORD_WEBHOOK= \
	$(PYTHON) main.py

clean:
	rm -rf $(VENV) __pycache__
