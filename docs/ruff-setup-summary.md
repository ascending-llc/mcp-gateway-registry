# Ruff Setup Summary

## ✅ What Was Added

### 1. **Ruff Configuration** ([pyproject.toml](../pyproject.toml))
   - Added Ruff linter and formatter configuration
   - Configured for Python 3.12 with 100-character line length
   - Enabled comprehensive rule sets (pycodestyle, Pyflakes, isort, pylint, etc.)
   - Configured per-file ignores for tests and scripts
   - Added Bandit configuration for security scanning

### 2. **Pre-commit Hooks** ([.pre-commit-config.yaml](../.pre-commit-config.yaml))
   - Ruff linting and formatting on commit
   - Basic file checks (trailing whitespace, YAML validation, etc.)
   - Bandit security scanning
   - Automatically formats code before committing

### 3. **Poe Tasks** (in [pyproject.toml](../pyproject.toml))
   - `uv run poe lint` - Check code for issues
   - `uv run poe lint-fix` - Auto-fix linting issues
   - `uv run poe format` - Format code
   - `uv run poe format-check` - Check formatting without modifying
   - `uv run poe lint-all` - Run linter with fixes + formatter

### 4. **Dev Dependencies**
   - Added `ruff>=0.8.0` to all sub-projects (registry, auth_server, packages)
   - Added `pre-commit>=4.0.0` to root workspace
   - Removed redundant tools (black, isort) from auth_server

### 5. **Documentation**
   - [Ruff Guide](../docs/ruff-guide.md) - Comprehensive usage guide
   - Setup script: [setup-ruff.sh](../scripts/setup-ruff.sh)

### 6. **GitHub Actions CI** ([.github/workflows/test.yml](../.github/workflows/test.yml))
   - Automated Ruff format checks on every PR
   - Automated Ruff linting on every PR
   - Bandit security scanning
   - Inline PR annotations for issues

## 🚀 Quick Start

### First-Time Setup

```bash
# Run the setup script
./scripts/setup-ruff.sh
```

This script will:
1. Install Ruff and pre-commit
2. Install pre-commit hooks
3. Run Ruff on all files for the first time
4. Format all code

### Daily Usage

```bash
# Before committing (recommended)
uv run poe lint-all

# Hooks will run automatically on commit
git add .
git commit -m "Your message"
```

## 📝 Key Features

### Comprehensive Linting Rules

Ruff replaces multiple tools with a single, fast linter:
- **Black** → `ruff format`
- **isort** → Import sorting included
- **Flake8** → Linting rules included
- **pyupgrade** → Modern Python syntax enforcement
- **autoflake** → Unused import removal

### Rule Categories Enabled

- **E, W**: pycodestyle (PEP 8 compliance)
- **F**: Pyflakes (undefined names, unused imports)
- **I**: isort (import organization)
- **N**: pep8-naming (naming conventions)
- **UP**: pyupgrade (modern Python idioms)
- **B**: bugbear (common bugs and design problems)
- **C4**: comprehensions (list/dict optimization)
- **PT**: pytest-style (test best practices)
- **RET**: return statements
- **SIM**: code simplification
- **ARG**: unused arguments
- **PTH**: pathlib usage
- **PL**: pylint rules
- **RUF**: Ruff-specific rules

### Smart Defaults

- Line length: 100 characters
- Python version: 3.12
- Test files have relaxed rules
- FastAPI-specific ignores (e.g., function calls in defaults)

## 🔧 Configuration Highlights

### Excluded Directories

Ruff skips these directories automatically:
```
.git, .ruff_cache, .venv, __pycache__
htmlcov, .pytest_cache, node_modules
frontend, data, logs, ssl, secrets
```

### Per-File Ignores

- **Tests**: Relaxed rules for assertions, magic values, unused arguments
- **Scripts**: Allow print statements and many arguments
- **CLI tools**: Less strict about argument counts

### Import Sorting

First-party packages recognized:
```python
from registry import ...     # First-party
from auth_server import ...  # First-party
from packages import ...     # First-party
```

## 🎯 Common Workflows

### Before Creating a PR

```bash
# Lint and format everything
uv run poe lint-all

# Run tests
uv run poe test-all

# Verify formatting (CI mode)
uv run ruff format --check .
```

### Fixing Specific Directories

```bash
# Fix one directory at a time
uv run ruff check --fix registry/
uv run ruff format registry/

# Fix specific file
uv run ruff check --fix path/to/file.py
uv run ruff format path/to/file.py
```

### Incremental Adoption

If you have many existing issues:

```bash
# Fix imports first
uv run ruff check --select I --fix .

# Fix unused variables
uv run ruff check --select F401 --fix .

# Fix one rule at a time
uv run ruff check --select <RULE> --fix .
```

## 🛠️ IDE Integration

### VS Code

Install the [Ruff extension](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff) and add to settings:

```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true
  }
}
```

### Other IDEs

See [docs/ruff-guide.md](../docs/ruff-guide.md) for PyCharm, Neovim, and others.

## 📊 Benefits

### Performance
- **10-100x faster** than Black, isort, and Flake8 combined
- Written in Rust for maximum speed
- Entire codebase lints in seconds

### Simplicity
- **One tool** instead of 5+ different linters/formatters
- **One configuration** instead of multiple config files
- **One command** to run everything

### Quality
- **Comprehensive rules** covering security, performance, style
- **Auto-fix** for most issues
- **Compatible** with Black formatting style

## 🔗 Resources

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Complete Usage Guide](../docs/ruff-guide.md)
- [Rule Reference](https://docs.astral.sh/ruff/rules/)
- [Configuration](../pyproject.toml)
- [Pre-commit Config](../.pre-commit-config.yaml)

## 🐛 Troubleshooting

### Pre-commit hook failing

Let it fix the files, then re-commit:
```bash
git commit -m "Your message"  # Fails and fixes files
git add .
git commit -m "Your message"  # Should pass now
```

### Too many errors

Fix incrementally:
```bash
# Run setup script to fix most issues
./scripts/setup-ruff.sh

# Or fix specific directories
uv run ruff check --fix registry/
```

### Want to disable a specific rule

Add to [pyproject.toml](../pyproject.toml):
```toml
[tool.ruff.lint]
ignore = [
    "RULE_CODE",  # Reason for ignoring
]
```

## 📞 Support

- See [docs/ruff-guide.md](../docs/ruff-guide.md) for detailed guide
- Check [pyproject.toml](../pyproject.toml) configuration
- Open an issue if you encounter problems
