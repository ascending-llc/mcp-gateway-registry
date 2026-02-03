# CI/CD - Ruff Linting Integration

## Overview

The GitHub Actions workflow now includes automated Ruff checks on every pull request and push to `main`. This ensures all code meets quality standards before merging.

## What Gets Checked

The `lint` job in [.github/workflows/test.yml](../.github/workflows/test.yml) performs:

### 1. Ruff Format Check ✨
```yaml
- name: Check code formatting with Ruff
  run: uv run ruff format --check .
```

**What it does**: Verifies that all Python files follow consistent formatting standards.

**If it fails**: Your code needs formatting. Run `uv run poe format` locally.

### 2. Ruff Lint Check 🔍
```yaml
- name: Lint code with Ruff
  run: uv run ruff check . --output-format=github
```

**What it does**: Checks for code quality issues, unused imports, naming conventions, and more.

**If it fails**: Review the annotations in your PR and run `uv run poe lint-fix` locally.

### 3. Bandit Security Scan 🔒
```yaml
- name: Security check with bandit
  run: |
    uv run bandit -r auth_server/ -f json -o bandit-report-auth.json
    uv run bandit -r registry/ -f json -o bandit-report.json
    uv run bandit -r packages/ -f json -o bandit-report-packages.json
```

**What it does**: Scans for common security issues in Python code.

**If it fails**: Review the bandit report artifacts to identify security concerns.

## Making Your PR Pass CI

### Before Pushing

Run these commands locally to catch issues early:

```bash
# Quick check - same as CI
uv run ruff format --check .
uv run ruff check .

# Fix everything automatically
uv run poe lint-all

# Verify it passes
uv run ruff format --check . && uv run ruff check . && echo "✅ Ready for PR!"
```

### Understanding CI Failures

#### Format Check Failed
```
Error: Some files are not formatted correctly
```

**Solution**:
```bash
uv run poe format
git add .
git commit -m "Format code with Ruff"
git push
```

#### Lint Check Failed
```
error: [RULE_CODE]: Description of the issue
```

**Solution**:
```bash
# Auto-fix what can be fixed
uv run poe lint-fix

# Review remaining issues and fix manually
uv run ruff check .

git add .
git commit -m "Fix linting issues"
git push
```

## CI Workflow Details

### Job: `lint`

**Runs on**: Every PR, push to main

**Steps**:
1. Checkout code
2. Install Python 3.12
3. Install `uv` package manager
4. Cache dependencies for speed
5. Install project dependencies
6. Run Ruff format check (fails PR if issues found)
7. Run Ruff lint check (fails PR if issues found)
8. Run Bandit security scan (doesn't fail PR)
9. Upload security reports as artifacts

### Performance

- **Caching**: Dependencies are cached for faster runs
- **Parallel execution**: Lint job runs in parallel with tests
- **Fast**: Ruff is 10-100x faster than traditional linters

### Inline Annotations

When linting fails, GitHub will show **inline annotations** on your PR:

```
registry/api/agent_routes.py
  Line 42: [F401] `typing.Optional` imported but unused
  Line 56: [E501] Line too long (105 > 100 characters)
```

Click on these to see exactly what needs fixing.

## Local Development Workflow

### Daily Workflow

```bash
# 1. Write code
vim registry/services/new_service.py

# 2. Format and lint
uv run poe lint-all

# 3. Commit (pre-commit hooks will also run)
git add .
git commit -m "Add new service"

# 4. Push (CI will verify)
git push
```

### Pre-commit Hooks

Pre-commit hooks run automatically on `git commit` and will:
- Format your code with Ruff
- Fix auto-fixable linting issues
- Run security checks

If hooks modify files:
```bash
git commit -m "Your message"  # Hooks run and modify files
git add .                      # Re-add modified files
git commit -m "Your message"  # Commit again
```

## Disabling CI Checks (Not Recommended)

If you need to bypass checks temporarily (e.g., work in progress):

```bash
# Skip pre-commit hooks (local only)
git commit --no-verify -m "WIP: work in progress"
```

**Note**: CI will still run on your PR. Consider using draft PRs instead.

## Troubleshooting

### "Ruff not found" in CI

This shouldn't happen as Ruff is installed via `uv sync`. If it does:

1. Check that Ruff is in `pyproject.toml` dev dependencies
2. Verify `uv sync --all-groups` is running in the workflow
3. Check the CI logs for installation errors

### Cache Issues

If dependencies aren't installing correctly:

1. Clear cache by updating the cache key in [.github/workflows/test.yml](../.github/workflows/test.yml)
2. Or manually clear caches in GitHub Actions settings

### False Positives

If Ruff flags something incorrectly:

1. Add a `# noqa: RULE_CODE` comment for that line
2. Or update the configuration in `pyproject.toml` to ignore that rule

Example:
```python
result = long_function_call(a, b, c, d, e)  # noqa: PLR0913
```

## Configuration

### Ruff Configuration

Located in [pyproject.toml](../pyproject.toml) under `[tool.ruff]`.

To modify rules:
```toml
[tool.ruff.lint]
ignore = [
    "RULE_CODE",  # Reason for ignoring
]
```

### CI Workflow Configuration

Located in [.github/workflows/test.yml](../.github/workflows/test.yml).

To modify the lint job, edit the `lint` section.

## Viewing CI Results

### In Pull Requests

1. Open your PR on GitHub
2. Scroll to the "Checks" section at the bottom
3. Click on the "Code Quality & Linting" check
4. View detailed logs and annotations

### Artifacts

After each run, you can download:
- **Bandit security reports** (JSON format)
- Check the "Artifacts" section in the workflow run

## Resources

- [GitHub Actions Workflow](../.github/workflows/test.yml)
- [Ruff Configuration](../pyproject.toml)
- [Ruff Usage Guide](./ruff-guide.md)
- [Ruff Documentation](https://docs.astral.sh/ruff/)

## Summary

✅ **Automated checks** on every PR  
✅ **Inline annotations** for easy fixes  
✅ **Fast execution** with caching  
✅ **Consistent quality** across the codebase  
✅ **Security scanning** included  

Run `uv run poe lint-all` before pushing to ensure your PR passes CI! 🚀
