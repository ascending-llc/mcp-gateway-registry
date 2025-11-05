# Release v1.0.5 - Supply Chain Security & MCP Registry CLI

**October 28, 2025**

---

## Major Features

### 🛡️ Supply Chain Security with Cisco AI Defence

Automated security scanning for MCP servers:
- **Automated scanning** on server registration
- **Continuous monitoring** with periodic audits
- **Dual analysis**: YARA pattern detection + LLM-powered threat analysis
- **Auto-disable** servers with security issues

[Security Scanner Guide](docs/security-scanner.md) | [Cisco MCP Scanner](https://github.com/cisco-ai-defense/mcp-scanner)

### 🤖 Interactive MCP Registry CLI

Talk to your MCP Registry in natural language:
- **Natural language discovery** - Ask questions in plain English
- **Real-time token tracking** - Auth status, validity, cost monitoring
- **AI-powered** - Works with Claude (Anthropic) and Amazon Bedrock
- **Global command** - `registry --url <gateway-url>`

[CLI Guide](docs/mcp-registry-cli.md)

---

## What's New

- ✅ Global `registry` CLI command
- ✅ Enhanced TokenStatusFooter with cost tracking
- ✅ Improved app initialization and error handling
- ✅ Updated README with CLI section and demo
- ✅ Auto token refresh at < 10 seconds remaining

---

## Credits

**Nisha Deborah Philips** [@nisha-deborah-philips](https://www.linkedin.com/in/nisha-deborah-philips/) - Cisco scanner integration, AI assistant, UI

**Kangheng Liu** [@kangheng-liu](https://www.linkedin.com/in/kangheng-liu/) - AI assistant & registry UI

**Abit** [@abiit](https://www.linkedin.com/in/abiit/) - Claude Code-like AI assistant concept

---

## Getting Started

**Security Scanning:**
```bash
./cli/service_mgmt.sh add <config-file> yara,llm
```

**CLI:**
```bash
cd cli && npm install && npm link
registry --url https://your-gateway.com
```

---

**Repository:** https://github.com/agentic-community/mcp-gateway-registry
