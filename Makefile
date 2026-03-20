.PHONY: install build dev start test lint format clean help

## install: Install all dependencies
install:
	npm install

## build: Compile TypeScript to JavaScript
build:
	npm run build

## dev: Start development server with hot reload
dev:
	npm run dev

## start: Start production server
start:
	npm run start

## test: Run tests
test:
	npm test

## test-coverage: Run tests with coverage report
test-coverage:
	npm run test:coverage

## lint: Run linter
lint:
	npm run lint

## lint-fix: Run linter and auto-fix issues
lint-fix:
	npm run lint:fix

## format: Format source files
format:
	npm run format

## type-check: Run TypeScript type checking
type-check:
	npm run type-check

## clean: Remove build artifacts
clean:
	npm run clean

## setup: Initial project setup (copy .env.example to .env)
setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example - please fill in your values"; \
	else \
		echo ".env already exists, skipping"; \
	fi

## help: Show this help message
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@grep -E '^## ' Makefile | sed 's/## /  /'
