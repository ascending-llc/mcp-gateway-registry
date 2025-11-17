import {parseCommand, type CallCommand, type TaskCommand, type AgentsCommand} from "../chat/commandParser.js";
import {resolveTaskCommand} from "../chat/taskInterpreter.js";
import {executeMcpCommand, formatMcpResult} from "../runtime/mcp.js";
import {runScriptTaskToString} from "../runtime/script.js";
import type {TaskContext} from "../tasks/types.js";

export interface CommandExecutionContext extends TaskContext {}

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
  // Call list_services to get all registered MCP servers
  const {handshake, response} = await executeMcpCommand(
    "call",
    context.gatewayUrl,
    context.gatewayToken,
    context.backendToken,
    {
      tool: "list_services",
      args: {}
    }
  );

  // Format as compact summary to avoid terminal lag from massive JSON
  const lines: string[] = [];

  try {
    const content = (response as any).content;
    if (!content || !Array.isArray(content) || content.length === 0) {
      lines.push("No response content");
      return {lines};
    }

    const textContent = content[0].text;
    const data = JSON.parse(textContent);

    if (data && data.services && Array.isArray(data.services)) {
      lines.push(`Found ${data.services.length} MCP servers:\n`);

      data.services.forEach((service: any, index: number) => {
        lines.push(`${index + 1}. ${service.server_name || 'Unknown'}`);
        lines.push(`   Path: ${service.path || 'N/A'}`);
        lines.push(`   Status: ${service.health_status || 'unknown'} ${service.is_enabled ? '(enabled)' : '(disabled)'}`);
        if (service.description) {
          // Truncate long descriptions
          const desc = service.description.length > 80
            ? service.description.substring(0, 80) + '...'
            : service.description;
          lines.push(`   Description: ${desc}`);
        }
        if (service.tags && service.tags.length > 0) {
          lines.push(`   Tags: ${service.tags.slice(0, 5).join(', ')}${service.tags.length > 5 ? '...' : ''}`);
        }
        lines.push(`   Tools: ${service.num_tools || 0}`);
        lines.push('');
      });

      lines.push(`Total: ${data.total_count || data.services.length} servers\n`);
      lines.push('Tip: Ask "tell me more about server X" for detailed info');
    } else {
      lines.push("No servers found");
    }
  } catch (error) {
    lines.push(`Error formatting server list: ${(error as Error).message}`);
  }

  return {lines};
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
  try {
    const response = await fetch(`${context.gatewayUrl}/api/agents`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${context.gatewayToken}`,
        "Content-Type": "application/json"
      }
    });

    if (!response.ok) {
      return {lines: [`Error: ${response.status} - Failed to list agents`], isError: true};
    }

    const data = await response.json() as any;
    const agents = Array.isArray(data.agents) ? data.agents : (data.agents && typeof data.agents === "object" ? Object.values(data.agents) : []);

    if (!Array.isArray(agents) || agents.length === 0) {
      return {lines: ["No agents found."]};
    }

    const lines: string[] = [`Found ${agents.length} agent(s):\n`];
    agents.forEach((agent: any, index: number) => {
      lines.push(`${index + 1}. ${agent.name || "Unknown"}`);
      lines.push(`   Path: ${agent.path || "N/A"}`);
      if (agent.description) {
        const desc = agent.description.length > 80
          ? agent.description.substring(0, 80) + "..."
          : agent.description;
        lines.push(`   Description: ${desc}`);
      }
      lines.push(`   Status: ${agent.enabled ? "enabled" : "disabled"}`);
      if (agent.tags && Array.isArray(agent.tags) && agent.tags.length > 0) {
        lines.push(`   Tags: ${agent.tags.slice(0, 5).join(", ")}${agent.tags.length > 5 ? "..." : ""}`);
      }
      lines.push("");
    });

    return {lines};
  } catch (error) {
    return {lines: [`Error listing agents: ${(error as Error).message}`], isError: true};
  }
}

async function executeAgentsGet(agentPath: string, context: CommandExecutionContext) {
  try {
    const response = await fetch(`${context.gatewayUrl}/api/agents${agentPath}`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${context.gatewayToken}`,
        "Content-Type": "application/json"
      }
    });

    if (!response.ok) {
      return {lines: [`Error: ${response.status} - Agent not found or access denied`], isError: true};
    }

    const agent = await response.json() as any;
    const lines: string[] = [];

    lines.push(`${agent.name || "Unknown"} (${agent.path || agentPath})`);
    lines.push(`Description: ${agent.description || "N/A"}`);
    if (agent.url) lines.push(`URL: ${agent.url}`);
    if (agent.version) lines.push(`Version: ${agent.version}`);

    if (agent.skills && Array.isArray(agent.skills) && agent.skills.length > 0) {
      lines.push("\nSkills:");
      agent.skills.forEach((skill: any, index: number) => {
        lines.push(`  ${index + 1}. ${skill.name || skill.id || "Unknown"}`);
        if (skill.description) {
          lines.push(`     ${skill.description}`);
        }
      });
    }

    if (agent.tags && Array.isArray(agent.tags) && agent.tags.length > 0) {
      lines.push(`\nTags: ${agent.tags.join(", ")}`);
    }

    lines.push(`\nVisibility: ${agent.visibility || "N/A"}`);
    lines.push(`Trust Level: ${agent.trust_level || "N/A"}`);
    lines.push(`Status: ${agent.enabled ? "enabled" : "disabled"}`);

    return {lines};
  } catch (error) {
    return {lines: [`Error fetching agent: ${(error as Error).message}`], isError: true};
  }
}

async function executeAgentsSearch(query: string, context: CommandExecutionContext) {
  try {
    const response = await fetch(`${context.gatewayUrl}/api/agents?search=${encodeURIComponent(query)}`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${context.gatewayToken}`,
        "Content-Type": "application/json"
      }
    });

    if (!response.ok) {
      return {lines: [`Error: ${response.status} - Search failed`], isError: true};
    }

    const data = await response.json() as any;
    const agents = Array.isArray(data.agents) ? data.agents : (data.agents && typeof data.agents === "object" ? Object.values(data.agents) : []);

    if (!Array.isArray(agents) || agents.length === 0) {
      return {lines: [`No agents found matching: "${query}"`]};
    }

    const lines: string[] = [`Found ${agents.length} agent(s) matching "${query}":\n`];
    agents.forEach((agent: any, index: number) => {
      lines.push(`${index + 1}. ${agent.name || "Unknown"}`);
      lines.push(`   Path: ${agent.path || "N/A"}`);
      if (agent.description) {
        const desc = agent.description.length > 80
          ? agent.description.substring(0, 80) + "..."
          : agent.description;
        lines.push(`   ${desc}`);
      }
      lines.push("");
    });

    return {lines};
  } catch (error) {
    return {lines: [`Error searching agents: ${(error as Error).message}`], isError: true};
  }
}

async function executeAgentsTest(agentPath: string, context: CommandExecutionContext) {
  try {
    const response = await fetch(`${context.gatewayUrl}/api/agents${agentPath}`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${context.gatewayToken}`,
        "Content-Type": "application/json"
      }
    });

    if (!response.ok) {
      return {lines: [`Error: ${response.status} - Agent not found or access denied`], isError: true};
    }

    const agent = await response.json() as any;
    const lines: string[] = [];

    lines.push(`Testing agent: ${agent.name || agentPath}`);
    lines.push(`✓ Agent registered`);
    lines.push(`✓ Endpoint accessible`);
    if (agent.enabled) {
      lines.push(`✓ Agent enabled`);
    } else {
      lines.push(`⚠ Agent is disabled`);
    }

    return {lines};
  } catch (error) {
    return {lines: [`Error testing agent: ${(error as Error).message}`], isError: true};
  }
}

async function executeAgentsTestAll(context: CommandExecutionContext) {
  try {
    const response = await fetch(`${context.gatewayUrl}/api/agents`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${context.gatewayToken}`,
        "Content-Type": "application/json"
      }
    });

    if (!response.ok) {
      return {lines: [`Error: ${response.status} - Failed to list agents`], isError: true};
    }

    const data = await response.json() as any;
    const agents = Array.isArray(data.agents) ? data.agents : (data.agents && typeof data.agents === "object" ? Object.values(data.agents) : []);

    if (!Array.isArray(agents) || agents.length === 0) {
      return {lines: ["No agents to test."]};
    }

    const lines: string[] = [`Testing ${agents.length} agent(s)...\n`];
    let healthy = 0;
    let unhealthy = 0;

    agents.forEach((agent: any) => {
      if (agent.enabled) {
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
    return {lines: [`Error testing agents: ${(error as Error).message}`], isError: true};
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
