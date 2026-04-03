.PHONY: help setup dev test lint format clean

# =============================================================================
# Setup
# =============================================================================

setup: ## Install all dependencies via uv
	uv sync --all-extras
	@echo "Setup complete. Run 'make dev' to start development."

# =============================================================================
# Development
# =============================================================================

dev: ## Start local dev server
	uv run uvicorn src.medbill.web.app:app --reload --host 0.0.0.0 --port 8000

# =============================================================================
# Quality
# =============================================================================

test: ## Run all tests
	uv run pytest tests/ -v -x

test-cov: ## Run tests with coverage
	uv run pytest tests/ -v --cov=src/medbill --cov-report=html

lint: ## Run linters and type checker
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy .

format: ## Auto-format code
	uv run ruff format .
	uv run ruff check --fix .

# =============================================================================
# Data Generation (MedBillGen)
# =============================================================================

generate-data: ## Generate 5,000 synthetic training documents
	uv run python -m medbillgen.cli generate \
		--count 5000 --output medbillgen/output/train --seed 42 \
		--augmentation mixed --error-rate 0.3
	uv run python -m medbillgen.cli generate \
		--count 500 --output medbillgen/output/val --seed 43 \
		--augmentation mixed --error-rate 0.3
	@echo "Generated 5,500 training + validation documents."

generate-bench: ## Generate 500 benchmark documents
	uv run python -m medbillgen.cli generate \
		--count 500 --output medbillbench/data/test --seed 44 \
		--augmentation tiered --error-rate 0.35 --benchmark-mode
	uv run python -m medbillbench.cli create-manifest
	@echo "Generated 500 benchmark documents with manifest."

# =============================================================================
# Benchmark (MedBillBench)
# =============================================================================

evaluate: ## Run MedBillBench on fine-tuned model
	uv run python -m medbillbench.cli evaluate \
		--model medbill-ocr \
		--model-path training/results/checkpoints/best \
		--data-dir medbillbench/data/test

evaluate-all: evaluate ## Run all model evaluations + leaderboard
	uv run python -m medbillbench.cli leaderboard --results-dir medbillbench/results/

# =============================================================================
# Training
# =============================================================================

train: ## Run LoRA fine-tune on GLM-OCR
	uv run python training/scripts/train.py \
		--config training/configs/lora_medbill.yaml \
		--data-dir training/data/llama_factory_format \
		--output-dir training/results/checkpoints/lora_r16_a32_e3
	@echo "Training complete. Run 'make evaluate' to benchmark."

# =============================================================================
# Build & Deploy
# =============================================================================

build: ## Build Docker image
	docker build -t medbill:latest .

docker-up: ## Run via Docker Compose
	docker compose up --build

# =============================================================================
# Utilities
# =============================================================================

clean: ## Clean generated artifacts
	rm -rf medbillgen/output/ medbillbench/results/ training/results/
	rm -rf dist/ build/ .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
