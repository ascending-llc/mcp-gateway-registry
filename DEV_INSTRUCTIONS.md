# Getting Started

## Prerequisite Reading
**READ THIS FIRST:** [CONTRIBUTING.md](CONTRIBUTING.md)

Before you start contributing, please review the project's contribution guidelines.

## Setup Instructions for Contributors

### Step 1: Choose Your Development Environment
We recommend the fastest option to get started:

#### Option A: macOS Setup (Fastest ⚡)
Complete this setup guide first:

- [macOS Setup Guide](macos-setup-guide.md)
- Time to first run: ~30 minutes

#### Option B: EC2 Complete Configuration (Preferred for Server Setup)
If working on EC2 or a Linux server, complete this guide first:

- [Complete Configuration Guide](complete-configuration-guide.md)
- Time to first run: ~60 minutes

## Before You Start Coding

### 1. Ask Your Coding Assistant to Read Documentation
Before making any code changes, ask your AI coding assistant to read:

**LLM/AI Documentation (Critical for understanding the project):**
- [docs/llms.txt](docs/llms.txt)

**Coding Standards and Guidelines:**
- [CLAUDE.md](CLAUDE.md) - Project-specific coding standards

### 2. Review the CLAUDE.md File
This project uses [CLAUDE.md](CLAUDE.md) for coding standards. The file is already included in the repository root - make sure to review it before contributing.

### 3. Set Up Pre-commit Hooks (Required)
This project uses Ruff for code linting and formatting. Install pre-commit hooks to automatically check your code before commits:

```bash
# Install pre-commit hooks (required for all developers)
uv run pre-commit install

# Test that hooks are working correctly
uv run pre-commit run --all-files
```

**What this does:**
- Automatically lints and formats your code before each commit
- Prevents commits with linting errors
- Ensures consistent code style across the project

**Manual linting commands (optional):**
```bash
# Check all files for linting issues
uv run poe lint-all

# Auto-fix linting issues where possible
uv run poe lint-fix

# Format code
uv run poe format
```

## Testing Your Changes

Before submitting a pull request, you must run and pass the test suite:

### Quick Start Testing
```bash
# Generate fresh credentials (tokens expire in 5 minutes)
./credentials-provider/generate_creds.sh

# Run tests locally (skip production for fast iteration)
./tests/run_all_tests.sh --skip-production
```

### For PR Merge (REQUIRED)
```bash
# Full test suite including production tests
./tests/run_all_tests.sh

# All tests must pass (0 failures) before merging
```

### Understanding the Tests
See the comprehensive testing documentation:

- **[tests/README.md](tests/README.md)** - Start here! Navigation guide with access control overview
- **[tests/TEST_QUICK_REFERENCE.md](tests/TEST_QUICK_REFERENCE.md)** - Quick reference for how-to guides
- **[tests/lob-bot-access-control-testing.md](tests/lob-bot-access-control-testing.md)** - Access control test details
- **[auth_server/scopes.yml](auth_server/scopes.yml)** - Permission definitions (admin, LOB1, LOB2)

### Common Testing Workflows

**Agent CRUD Testing:**
```bash
./credentials-provider/generate_creds.sh
bash tests/agent_crud_test.sh
```

**Access Control Testing (LOB Bots):**
```bash
./keycloak/setup/generate-agent-token.sh admin-bot
./keycloak/setup/generate-agent-token.sh lob1-bot
./keycloak/setup/generate-agent-token.sh lob2-bot
bash tests/run-lob-bot-tests.sh
```

**Check Test Logs:**
```bash
ls -lh /tmp/*_*.log
grep -i "error\|fail" /tmp/*.log
```

## Fork and Contribute

### Repository Access
**Important:** There is no direct access to this repository. To contribute:

1. **Fork the repository on GitHub**
   ```
   https://github.com/agentic-community/mcp-gateway-registry
   ```

2. **Clone your fork locally**
   ```bash
   git clone https://github.com/YOUR-USERNAME/mcp-gateway-registry.git
   cd mcp-gateway-registry
   ```

3. **Create a feature branch**
   ```bash
   git checkout -b feat/your-feature-name
   ```

4. **Make your changes** following the coding standards in CLAUDE.md

5. **Commit and push to your fork**
   ```bash
   git push origin feat/your-feature-name
   ```

6. **Create a Pull Request** to the main repository
   - Use a clear, descriptive PR title
   - Reference any related issues
   - Include test results and screenshots if applicable

## Development Checklist
Before submitting a pull request:

- [ ] Completed one of the setup guides (macOS or EC2)
- [ ] Read docs/llms.txt
- [ ] Read CLAUDE.md (coding standards)
- [ ] Installed pre-commit hooks: `uv run pre-commit install`
- [ ] Code follows project conventions (Ruff linting passes)
- [ ] Generated fresh credentials: `./credentials-provider/generate_creds.sh`
- [ ] Local tests pass: `./tests/run_all_tests.sh --skip-production`
- [ ] PR merge tests pass: `./tests/run_all_tests.sh` (all tests must pass)
- [ ] Reviewed test documentation: [tests/README.md](tests/README.md)
- [ ] Changes are pushed to a fork, not directly to this repo
- [ ] Pull request is created with clear description

## Questions?
- Check the [CONTRIBUTING.md](CONTRIBUTING.md) file for more details
- Review existing PRs to see contribution patterns
- Ask your coding assistant to review the documentation with you

Happy coding! 🚀
