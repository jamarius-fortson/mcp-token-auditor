# Makefile for MCP Token Auditor

.PHONY: install dev test lint format clean run health

# Default target
.DEFAULT_GOAL := help

help:
	@echo "MCP Token Auditor - Development Commands"
	@echo ""
	@echo "  make install       Install dependencies"
	@echo "  make dev           Run development server with auto-reload"
	@echo "  make test          Run test suite"
	@echo "  make test-cov      Run tests with coverage report"
	@echo "  make lint          Run type checking and linting"
	@echo "  make format        Auto-format code"
	@echo "  make clean         Remove cache and artifacts"
	@echo "  make run           Run production server"
	@echo "  make health        Check server health"
	@echo ""

install:
	pip install -r requirements.txt

dev:
	python -m uvicorn src.main:MCPTokenAuditorApp.app --reload --host 127.0.0.1 --port 8765

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=src --cov-report=html

lint:
	mypy src/

format:
	black src/ tests/
	isort src/ tests/

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

run:
	python -m src.main

health:
	curl -s http://127.0.0.1:8765/health | python -m json.tool
