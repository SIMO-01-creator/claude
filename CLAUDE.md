# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
npm install

# Development (hot reload)
npm run dev

# Build
npm run build

# Run tests
npm test

# Run a single test file
npx jest src/path/to/file.test.ts

# Run tests matching a name pattern
npx jest -t "test name pattern"

# Lint
npm run lint
npm run lint:fix

# Type-check without emitting
npm run type-check

# Format
npm run format
```

## Architecture

This is a TypeScript project using the Anthropic SDK (`@anthropic-ai/sdk`). Source files live in `src/`, compiled output goes to `dist/`.

- `src/index.ts` — entry point; instantiates `Anthropic` client and calls the messages API
- Tests live alongside source files as `*.test.ts` or `*.spec.ts`
- `tsx` is used for development (no compile step); `tsc` compiles for production

The `Anthropic` client reads `ANTHROPIC_API_KEY` from the environment automatically. Copy `.env.example` to `.env` and set the key before running.
