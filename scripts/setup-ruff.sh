#!/bin/bash
# Setup script for Ruff and pre-commit hooks

set -e

echo "🚀 Setting up Ruff linting and pre-commit hooks..."
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ Error: uv is not installed. Please install it first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "📦 Installing dependencies (including Ruff and pre-commit)..."
uv sync

echo ""
echo "🔧 Installing pre-commit hooks..."
uv run pre-commit install

echo ""
echo "🧹 Running Ruff on all files for the first time..."
echo "   This may show many issues - don't worry, we'll fix them!"
echo ""

# Run linting with fixes
if uv run ruff check --fix .; then
    echo "✅ Ruff linting passed!"
else
    echo "⚠️  Some linting issues found. Running formatter..."
fi

# Run formatting
echo ""
echo "✨ Formatting code..."
uv run ruff format .

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Available commands:"
echo "  uv run poe lint          # Check for issues"
echo "  uv run poe lint-fix      # Check and auto-fix issues"
echo "  uv run poe format        # Format code"
echo "  uv run poe lint-all      # Lint + format (recommended before commit)"
echo ""
echo "Pre-commit hooks are now installed and will run automatically on git commit."
echo "To run pre-commit manually: uv run pre-commit run --all-files"
echo ""
echo "📖 For more information, see: docs/ruff-guide.md"
