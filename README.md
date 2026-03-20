# Claude

A TypeScript project for building with the Claude API.

## Prerequisites

- [Node.js](https://nodejs.org/) >= 18
- npm >= 9

## Setup

1. **Clone the repository**

   ```bash
   git clone <repo-url>
   cd claude
   ```

2. **Install dependencies**

   ```bash
   make install
   # or: npm install
   ```

3. **Configure environment**

   ```bash
   make setup
   # Then edit .env with your values:
   # ANTHROPIC_API_KEY=your_api_key_here
   ```

## Development

```bash
# Start development server with hot reload
make dev

# Type-check
make type-check

# Run linter
make lint

# Format code
make format
```

## Testing

```bash
# Run tests
make test

# Run tests with coverage
make test-coverage
```

## Building

```bash
# Compile TypeScript
make build

# Start production build
make start
```

## Project Structure

```
├── src/               # Source files
│   └── index.ts       # Application entry point
├── dist/              # Compiled output (generated)
├── coverage/          # Test coverage reports (generated)
├── .env.example       # Environment variable template
├── .eslintrc.json     # ESLint configuration
├── .prettierrc        # Prettier configuration
├── jest.config.ts     # Jest configuration
├── Makefile           # Development shortcuts
├── package.json       # Dependencies and scripts
└── tsconfig.json      # TypeScript configuration
```

## Available Commands

Run `make help` to see all available commands.
