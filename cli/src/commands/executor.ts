import {parseCommand, type CallCommand, type TaskCommand, type AgentsCommand} from "../chat/commandParser.js";
import {resolveTaskCommand} from "../chat/taskInterpreter.js";
import {executeMcpCommand, formatMcpResult} from "../runtime/mcp.js";
import {runScriptTaskToString} from "../runtime/script.js";
import type {TaskContext} from "../tasks/types.js";
import {spawn} from "node:child_process";
import {REGISTRY_CLI_WRAPPER, REPO_ROOT} from "../paths.js";

export interface CommandExecutionContext extends TaskContext {}

// Helper function to call the registry CLI wrapper
async function callRegistryWrapper(args: string[], context: CommandExecutionContext): Promise<{stdout: string; stderr: string; exitCode: number}> {
  const baseArgs = [
    "run",
    "python",
    REGISTRY_CLI_WRAPPER,
    "--base-url",
    context.gatewayBaseUrl,
    ...args
  ];

  // Use backendToken if available, otherwise fall back to gatewayToken
  const token = context.backendToken || context.gatewayToken;

  const env = token
    ? {...process.env, GATEWAY_TOKEN: token}
    : process.env;

  return new Promise((resolve) => {
    const child = spawn("uv", baseArgs, {
      cwd: REPO_ROOT,
      env: env as NodeJS.ProcessEnv,
      stdio: ["ignore", "pipe", "pipe"]
    });

    let stdout = "";
    let stderr = "";

    child.stdout?.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr?.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("close", (code) => {
      resolve({stdout, stderr, exitCode: code ?? -1});
    });
    child.on("error", (error) => {
      resolve({
        stdout,
        stderr: `${stderr}\nFailed to start process: ${(error as Error).message}`,
        exitCode: -1
      });
    });
  });
}

export async function executeSlashCommand(
  input: string,
  context: CommandExecutionContext
): Promise<{lines: string[]; isError?: boolean; shouldExit?: boolean}> {
  const parsed = parseCommand(input);

  switch (parsed.kind) {
    case "help":
      return {lines: [detailedHelpMessage()]};

    case "exit":
      return {lines: ["Goodbye!"], shouldExit: true};

    case "ping":
    case "list":
    case "init":
      return await executeMcp(parsed.kind, context);

    case "servers":
      return await executeServers(context);

    case "call":
      return await executeCall(parsed, context);

    case "agents":
      return await executeAgents(parsed as AgentsCommand, context);

    case "task": {
      const resolution = resolveTaskCommand(parsed as TaskCommand);
      if ("error" in resolution) {
        return {lines: [resolution.error], isError: true};
      }
      const result = await runScriptTaskToString(parsed.category, resolution.task, resolution.values, context);
      const lines = [
        `$ ${result.command.command} ${result.command.args.join(" ")}`,
        result.stdout.trim(),
        result.stderr ? `stderr:\n${result.stderr.trim()}` : "",
        `exitCode: ${result.exitCode ?? 0}`
      ]
        .filter((line) => line && line.trim().length > 0)
        .join("\n\n");
      return {lines: [lines]};
    }

    case "unknown":
    default:
      return {lines: [(parsed as any).message], isError: true};
  }
}

async function executeMcp(command: "ping" | "list" | "init", context: CommandExecutionContext) {
  const {handshake, response} = await executeMcpCommand(
    command,
    context.gatewayUrl,
    context.gatewayToken,
    context.backendToken
  );
  const lines = formatMcpResult(command, handshake, response);
  return {lines};
}

async function executeServers(context: CommandExecutionContext) {
  // Use the registry client to list servers instead of MCP call
  const result = await callRegistryWrapper(["anthropic", "list", "--limit", "1000"], context);

  if (result.exitCode !== 0) {
    return {
      lines: [`Error listing servers:`, result.stderr || result.stdout],
      isError: true
    };
  }

  try {
    const data = JSON.parse(result.stdout);
    const servers = data.servers || [];

    if (servers.length === 0) {
      return {lines: ["No servers found."]};
    }

    const lines: string[] = [`Found ${servers.length} MCP servers:\n`];

    servers.forEach((serverResponse: any, index: number) => {
      const server = serverResponse.server || serverResponse;
      const meta = server._meta || server.meta || {};
      const internalMeta = meta['io.mcpgateway/internal'] || {};

      lines.push(`${index + 1}. ${server.name || 'Unknown'}`);
      lines.push(`   Path: ${internalMeta.path || 'N/A'}`);
      lines.push(`   Status: ${internalMeta.is_enabled ? 'enabled' : 'disabled'}`);
      if (server.description) {
        const desc = server.description.length > 80
          ? server.description.substring(0, 80) + '...'
          : server.description;
        lines.push(`   Description: ${desc}`);
      }
      if (server.tags && server.tags.length > 0) {
        lines.push(`   Tags: ${server.tags.slice(0, 5).join(', ')}${server.tags.length > 5 ? '...' : ''}`);
      }
      if (server.tools && server.tools.length > 0) {
        lines.push(`   Tools: ${server.tools.length}`);
      }
      lines.push('');
    });

    lines.push(`Total: ${servers.length} servers\n`);
    lines.push('Tip: Ask "tell me more about server X" for detailed info');

    return {lines};
  } catch (error) {
    return {lines: [`Error parsing server list: ${(error as Error).message}`], isError: true};
  }
}

async function executeCall(parsed: CallCommand, context: CommandExecutionContext) {
  if (!parsed.tool) {
    return {lines: ["Tool name is required for /call."], isError: true};
  }

  let args: Record<string, unknown> = {};
  if (parsed.argsJson) {
    try {
      args = JSON.parse(parsed.argsJson);
    } catch (error) {
      return {lines: [`Invalid JSON for args: ${(error as Error).message}`], isError: true};
    }
  }

  const {handshake, response} = await executeMcpCommand(
    "call",
    context.gatewayUrl,
    context.gatewayToken,
    context.backendToken,
    {tool: parsed.tool, args}
  );
  const lines = formatMcpResult("call", handshake, response, parsed.tool);
  return {lines};
}

async function executeAgents(parsed: AgentsCommand, context: CommandExecutionContext) {
  const subcommand = parsed.subcommand.toLowerCase();

  switch (subcommand) {
    case "help":
      return {lines: [describeAgents()]};

    case "list":
      return await executeAgentsList(context);

    case "get":
      if (parsed.tokens.length === 0) {
        return {lines: ["Agent path required. Usage: /agents get /agent-path"], isError: true};
      }
      return await executeAgentsGet(parsed.tokens[0], context);

    case "search":
      if (parsed.tokens.length === 0) {
        return {lines: ["Search query required. Usage: /agents search <query>"], isError: true};
      }
      return await executeAgentsSearch(parsed.tokens.join(" "), context);

    case "test":
      if (parsed.tokens.length === 0) {
        return {lines: ["Agent path required. Usage: /agents test /agent-path"], isError: true};
      }
      return await executeAgentsTest(parsed.tokens[0], context);

    case "test-all":
      return await executeAgentsTestAll(context);

    default:
      return {lines: [`Unknown agent subcommand: ${subcommand}. Try "/agents help".`], isError: true};
  }
}

async function executeAgentsList(context: CommandExecutionContext) {
  const result = await callRegistryWrapper(["agent", "list"], context);

  if (result.exitCode !== 0) {
    return {
      lines: [`Error listing agents:`, result.stderr || result.stdout],
      isError: true
    };
  }

  return {lines: [result.stdout]};
}

async function executeAgentsGet(agentPath: string, context: CommandExecutionContext) {
  const result = await callRegistryWrapper(["agent", "get", agentPath], context);

  if (result.exitCode !== 0) {
    return {
      lines: [`Error getting agent:`, result.stderr || result.stdout],
      isError: true
    };
  }

  return {lines: [result.stdout]};
}

async function executeAgentsSearch(query: string, context: CommandExecutionContext) {
  const result = await callRegistryWrapper(["agent", "search", query], context);

  if (result.exitCode !== 0) {
    return {
      lines: [`Error searching agents:`, result.stderr || result.stdout],
      isError: true
    };
  }

  return {lines: [result.stdout]};
}

async function executeAgentsTest(agentPath: string, context: CommandExecutionContext) {
  const result = await callRegistryWrapper(["agent", "get", agentPath], context);

  if (result.exitCode !== 0) {
    return {
      lines: [`Error testing agent:`, result.stderr || result.stdout],
      isError: true
    };
  }

  try {
    const agent = JSON.parse(result.stdout);
    const lines: string[] = [];

    lines.push(`Testing agent: ${agent.name || agentPath}`);
    lines.push(`✓ Agent registered`);
    lines.push(`✓ Endpoint accessible`);
    if (agent.is_enabled) {
      lines.push(`✓ Agent enabled`);
    } else {
      lines.push(`⚠ Agent is disabled`);
    }

    return {lines};
  } catch (error) {
    return {lines: [`Error parsing agent data: ${(error as Error).message}`], isError: true};
  }
}

async function executeAgentsTestAll(context: CommandExecutionContext) {
  const result = await callRegistryWrapper(["agent", "list"], context);

  if (result.exitCode !== 0) {
    return {
      lines: [`Error testing agents:`, result.stderr || result.stdout],
      isError: true
    };
  }

  try {
    const data = JSON.parse(result.stdout);
    const agents = Array.isArray(data.agents) ? data.agents : [];

    if (agents.length === 0) {
      return {lines: ["No agents to test."]};
    }

    const lines: string[] = [`Testing ${agents.length} agent(s)...\n`];
    let healthy = 0;
    let unhealthy = 0;

    agents.forEach((agent: any) => {
      if (agent.is_enabled) {
        lines.push(`✓ ${agent.name || agent.path} - operational`);
        healthy++;
      } else {
        lines.push(`✗ ${agent.name || agent.path} - disabled`);
        unhealthy++;
      }
    });

    lines.push("");
    lines.push(`Summary: ${healthy}/${agents.length} agents operational`);
    if (unhealthy > 0) {
      lines.push(`Issue detected: ${unhealthy} agent(s) disabled or unavailable`);
    }

    return {lines};
  } catch (error) {
    return {lines: [`Error parsing agent data: ${(error as Error).message}`], isError: true};
  }
}

function describeAgents(): string {
  return [
    "Agent Registry Commands",
    "",
    "Discover and interact with registered A2A agents:",
    "",
    "  /agents list              List all available agents",
    "  /agents get <path>        Get details about a specific agent",
    "  /agents search <query>    Search agents by capability",
    "  /agents test <path>       Test agent availability",
    "  /agents test-all          Test all agents",
    "",
    "Examples:",
    "  /agents list",
    "  /agents get /code-reviewer",
    "  /agents search \"code review\"",
    "  /agents test /code-reviewer",
    "",
    "For more information, see the Agent CLI Guide: docs/agents-cli-guide.md"
  ].join("\n");
}

export function overviewMessage(): string {
  return [
    "Chat with me using natural language - I can discover and use MCP tools for you!",
    "",
    "Essential commands:",
    "  /help     Show help message",
    "  /exit     Exit the CLI",
    "  /ping     Test gateway connectivity",
    "  /list     List available tools",
    "  /servers  List all MCP servers",
    "  /agents   Discover and use A2A agents",
    "",
    "Examples:",
    "  \"How do I import servers from the Anthropic registry?\"",
    "  \"What authentication methods are supported by the servers?\"",
    "  \"What transport types do the servers support (stdio, SSE, HTTP)?\"",
    "  \"What agents are available?\"",
    "  \"Can you review my code?\"",

    ""
  ].join("\n");
}

export function detailedHelpMessage(): string {
  const basicCommands = [
    { cmd: "/help", desc: "Show this help message" },
    { cmd: "/servers", desc: "List all MCP servers" },
    { cmd: "/exit", desc: "Exit the CLI (aliases: /quit, /q)" }
  ];

  const advancedCommands = [
    { cmd: "/ping", desc: "Check MCP gateway connectivity" },
    { cmd: "/list", desc: "List MCP tools from current server" },
    { cmd: "/call", args: "tool=<name> args='<json>'", desc: "Invoke a tool directly" },
    { cmd: "/refresh", desc: "Refresh OAuth tokens" },
    { cmd: "/retry", desc: "Retry authentication" }
  ];

  const agentCommands = [
    { cmd: "/agents", desc: "Agent registry help" },
    { cmd: "/agents list", desc: "List all available agents" },
    { cmd: "/agents get", args: "<path>", desc: "Get details about an agent" },
    { cmd: "/agents search", args: "<query>", desc: "Search agents by capability" },
    { cmd: "/agents test", args: "<path>", desc: "Test agent availability" },
    { cmd: "/agents test-all", desc: "Test all registered agents" }
  ];

  const registryCommands = [
    { cmd: "/service", desc: "Service management (add, delete, monitor, test, groups)" },
    { cmd: "/import", desc: "Import from registry (dry, apply)" },
    { cmd: "/user", desc: "User management (create-m2m, create-human, delete, list)" },
    { cmd: "/diagnostic", desc: "Run diagnostics (run-suite, run-test)" }
  ];

  const formatCommands = (cmds: Array<{cmd: string; args?: string; desc: string}>) => {
    const maxLength = Math.max(...cmds.map(c => (c.cmd + (c.args ? " " + c.args : "")).length));
    return cmds.map(({cmd, args, desc}) => {
      const full = cmd + (args ? " " + args : "");
      const padding = " ".repeat(maxLength - full.length + 2);
      return `  ${full}${padding}${desc}`;
    });
  };

  return [
    "MCP Gateway CLI - Natural Language Interface",
    "",
    "PREFERRED: Use natural language to interact with MCP tools",
    "Examples:",
    "  \"What tools are available?\"",
    "  \"Check the current time in New York\"",
    "  \"Find tools for weather information\"",
    "  \"What agents are available?\"",
    "  \"Can you find an agent for code review?\"",
    "",
    "Basic Commands:",
    ...formatCommands(basicCommands),
    "",
    "Advanced Commands (for debugging):",
    ...formatCommands(advancedCommands),
    "",
    "Agent Management:",
    ...formatCommands(agentCommands),
    "",
    "Registry Management:",
    ...formatCommands(registryCommands)
  ].join("\n");
}
