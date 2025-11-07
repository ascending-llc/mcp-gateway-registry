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
- [ ] Code follows project conventions (use ruff, mypy, pytest)
- [ ] All tests pass locally
- [ ] Changes are pushed to a fork, not directly to this repo
- [ ] Pull request is created with clear description

## Questions?
- Check the [CONTRIBUTING.md](CONTRIBUTING.md) file for more details
- Review existing PRs to see contribution patterns
- Ask your coding assistant to review the documentation with you

Happy coding! 🚀
