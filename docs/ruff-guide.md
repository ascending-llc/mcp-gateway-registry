# Ruff Linting & Formatting Guide

This project uses [Ruff](https://docs.astral.sh/ruff/) - an extremely fast Python linter and code formatter written in Rust. Ruff replaces multiple tools (Black, isort, Flake8, and more) with a single, fast tool.

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Pre-commit Hooks](#pre-commit-hooks)
- [IDE Integration](#ide-integration)
- [Configuration](#configuration)
- [Common Issues](#common-issues)

## Quick Start

```bash
# Install dependencies (includes Ruff)
uv sync

# Check code for issues
uv run poe lint

# Fix auto-fixable issues
uv run poe lint-fix

# Format code
uv run poe format

# Do everything at once (lint with fixes + format)
uv run poe lint-all
```

## Installation

Ruff is included in the project's dev dependencies and will be installed automatically:

```bash
# Install all dependencies including dev dependencies
uv sync

# Verify Ruff is installed
uv run ruff --version
```

## Usage

### Available Commands

We've configured several poe tasks for convenience:

```bash
# Linting
uv run poe lint          # Check code for issues (no modifications)
uv run poe lint-fix      # Check and auto-fix issues
uv run poe lint-all      # Lint with fixes + format (recommended before commit)

# Formatting
uv run poe format        # Format all Python files
uv run poe format-check  # Check formatting without modifying files
```

### Direct Ruff Commands

You can also run Ruff directly:

```bash
# Linting
uv run ruff check .                  # Check all files
uv run ruff check path/to/file.py    # Check specific file
uv run ruff check --fix .            # Auto-fix issues

# Formatting
uv run ruff format .                 # Format all files
uv run ruff format path/to/file.py   # Format specific file
uv run ruff format --check .         # Check formatting (CI mode)

# Get help
uv run ruff check --help
uv run ruff format --help
```

### Targeting Specific Directories

```bash
# Lint specific packages
uv run ruff check registry/
uv run ruff check auth_server/
uv run ruff check packages/

# Format specific directories
uv run ruff format registry/services/
uv run ruff format tests/
```

## Pre-commit Hooks

Pre-commit hooks automatically run Ruff before each commit to ensure code quality.

### Initial Setup

```bash
# Install pre-commit (included in dev dependencies)
uv sync

# Install the git hooks
uv run pre-commit install
```

### Using Pre-commit

Once installed, pre-commit will automatically run on `git commit`:

```bash
# Hooks run automatically
git add .
git commit -m "Your message"

# If hooks fail, files will be modified
# Review changes and commit again
git add .
git commit -m "Your message"
```

### Manual Pre-commit Runs

```bash
# Run on all files (useful first time or after config changes)
uv run pre-commit run --all-files

# Run on staged files only
uv run pre-commit run

# Update hook versions
uv run pre-commit autoupdate

# Skip hooks temporarily (not recommended)
git commit --no-verify -m "Emergency fix"
```

## IDE Integration

### VS Code

1. Install the [Ruff extension](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)

2. Add to `.vscode/settings.json`:

```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },
  "ruff.nativeServer": true,
  "ruff.importStrategy": "fromEnvironment"
}
```

### PyCharm / IntelliJ IDEA

1. Go to **Settings** → **Tools** → **External Tools**
2. Click **+** to add a new tool:
   - **Name**: Ruff Check
   - **Program**: `$ProjectFileDir$/.venv/bin/ruff`
   - **Arguments**: `check --fix $FilePath$`
   - **Working directory**: `$ProjectFileDir$`

3. Add another tool for formatting:
   - **Name**: Ruff Format
   - **Program**: `$ProjectFileDir$/.venv/bin/ruff`
   - **Arguments**: `format $FilePath$`
   - **Working directory**: `$ProjectFileDir$`

### Neovim

Using `null-ls` or `none-ls`:

```lua
require("null-ls").setup({
  sources = {
    require("null-ls").builtins.formatting.ruff,
    require("null-ls").builtins.diagnostics.ruff,
  },
})
```

Or with native LSP:

```lua
require('lspconfig').ruff_lsp.setup({
  init_options = {
    settings = {
      args = {},
    }
  }
})
```

## Configuration

Ruff is configured in the root [`pyproject.toml`](../pyproject.toml) file. Key settings:

### Line Length

```toml
[tool.ruff]
line-length = 100
```

### Python Version

```toml
[tool.ruff]
target-version = "py312"
```

### Enabled Rules

We enable comprehensive rule sets including:
- **E, W**: pycodestyle errors and warnings
- **F**: Pyflakes (undefined names, unused imports)
- **I**: isort (import sorting)
- **N**: pep8-naming (naming conventions)
- **UP**: pyupgrade (modern Python syntax)
- **B**: flake8-bugbear (bug and design problems)
- **C4**: flake8-comprehensions (list/dict comprehensions)
- **PT**: flake8-pytest-style
- **RET**: flake8-return (return statements)
- **SIM**: flake8-simplify (code simplification)
- **ARG**: flake8-unused-arguments
- **PTH**: flake8-use-pathlib
- **PL**: Pylint rules
- **RUF**: Ruff-specific rules

### Ignored Rules

Some rules are intentionally ignored:

```toml
[tool.ruff.lint]
ignore = [
    "E501",    # Line too long (handled by formatter)
    "B008",    # Function calls in argument defaults (FastAPI Depends)
    "ARG001",  # Unused function argument (FastAPI dependencies)
    "PLR0913", # Too many arguments
    "PLR2004", # Magic value in comparison
]
```

### Per-File Rules

Test files and scripts have relaxed rules:

```toml
[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["PLR2004", "S101", "ARG001"]
"scripts/**/*.py" = ["T201"]  # Allow print statements
```

### Import Sorting

```toml
[tool.ruff.lint.isort]
known-first-party = ["registry", "auth_server", "packages", "servers"]
```

## Common Issues

### Issue: "Line too long" errors

**Solution**: Ruff's formatter will handle most line length issues. Run `uv run poe format`.

### Issue: Import order violations

**Solution**: Ruff automatically fixes import order with `--fix`:

```bash
uv run ruff check --fix .
```

### Issue: Too many linting errors in existing code

**Solution**: Fix incrementally:

```bash
# Fix one directory at a time
uv run ruff check --fix registry/
uv run ruff check --fix auth_server/

# Or fix specific rule violations
uv run ruff check --select F401 --fix .  # Fix unused imports
uv run ruff check --select I --fix .     # Fix import sorting
```

### Issue: Pre-commit hook failing

**Solution**: Let pre-commit fix the files, then re-add and commit:

```bash
git add .
git commit -m "Your message"
# Hook runs and modifies files
git add .
git commit -m "Your message"
# Should pass now
```

### Issue: Want to temporarily disable a rule

Add a `noqa` comment:

```python
# Disable specific rule
result = function_with_many_args(a, b, c, d, e, f)  # noqa: PLR0913

# Disable all rules for line
x = 1 / 0  # noqa

# Disable for entire file (at top)
# ruff: noqa
```

### Issue: Ruff and existing tools conflict

Ruff replaces:
- **Black** → Use `ruff format` instead
- **isort** → Use `ruff check --select I --fix` instead
- **Flake8** → Use `ruff check` instead
- **pyupgrade** → Included in Ruff's `UP` rules
- **autoflake** → Included in Ruff's `F` rules

Remove old tools from your workflow and use Ruff exclusively.

## CI/CD Integration

Ruff checks are integrated into the GitHub Actions workflow at [.github/workflows/test.yml](../.github/workflows/test.yml).

### What Gets Checked

On every pull request and push to main, the CI runs:

1. **Ruff Format Check** - Ensures all code is properly formatted
2. **Ruff Lint Check** - Checks for code quality issues
3. **Bandit Security Scan** - Checks for security vulnerabilities

### CI Workflow

```yaml
- name: Check code formatting with Ruff
  run: uv run ruff format --check .

- name: Lint code with Ruff
  run: uv run ruff check . --output-format=github
```

The `--output-format=github` flag provides inline annotations on your PR when issues are found.

### Making CI Pass

Before pushing your PR, ensure it will pass CI:

```bash
# Run the same checks as CI
uv run ruff format --check .  # Check formatting
uv run ruff check .           # Check linting

# Or fix issues automatically
uv run poe lint-all           # Fix and format everything
```

### GitHub Actions Example

The project includes a complete CI workflow. View it at:
- [.github/workflows/test.yml](../.github/workflows/test.yml)

Key features:
- Runs on all PRs and pushes to main
- Uses `uv` for fast dependency installation
- Caches dependencies for speed
- Provides inline PR annotations for issues
- Uploads security scan results

### Pre-merge Checks

Before creating a PR, run:

```bash
# Check everything
uv run poe lint-all

# Run tests
uv run poe test-all

# Check for errors
uv run ruff check .
uv run ruff format --check .
```

## Resources

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Ruff Rules Reference](https://docs.astral.sh/ruff/rules/)
- [Ruff vs Other Tools](https://docs.astral.sh/ruff/faq/#how-does-ruff-compare-to-other-tools)
- [Configuration Options](https://docs.astral.sh/ruff/configuration/)

## Support

For project-specific questions or issues:
1. Check the [configuration in pyproject.toml](../pyproject.toml)
2. Review [pre-commit config](./.pre-commit-config.yaml)
3. Open an issue in the project repository
