import {parseCommand, type CallCommand, type TaskCommand} from "../chat/commandParser.js";
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
      return {lines: [parsed.message], isError: true};
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
    "",
    "Examples:",
    "  \"How do I import servers from the Anthropic registry?\"",
    "  \"What authentication methods are supported by the servers?\"",
    "  \"What transport types do the servers support (stdio, SSE, HTTP)?\"",

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
    "",
    "Basic Commands:",
    ...formatCommands(basicCommands),
    "",
    "Advanced Commands (for debugging):",
    ...formatCommands(advancedCommands),
    "",
    "Registry Management:",
    ...formatCommands(registryCommands)
  ].join("\n");
}
