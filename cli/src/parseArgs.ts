export type CommandName = "ping" | "list" | "call" | "init";

export interface ParsedArgs {
  url?: string;
  tokenFile?: string;
  token?: string;
  command?: CommandName;
  tool?: string;
  args?: string;
  json?: boolean;
  interactive: boolean;
  helpRequested?: boolean;
  unknown: string[];
}

const COMMANDS = new Set<CommandName>(["ping", "list", "call", "init"]);

export const HELP_TEXT = `
Usage
  mcp-ink [options] [command]

Commands
  ping             Test connectivity with the configured MCP gateway
  list             List available tools for the current session
  call             Invoke a specific tool (use --tool and --args)
  init             Initialize the session and print the handshake payload

Options
  --url, -u <url>          Override the MCP gateway URL (default: http://localhost/mcpgw/mcp)
  --token-file, -t <path>  Path to a file containing a bearer token
  --token <value>          Explicit bearer token (overrides token file)
  --command <name>         Run a command non-interactively (alias for specifying the command positionally)
  --tool <name>            Tool name for the call command
  --args <json>            JSON string with tool arguments for the call command
  --json                   Print raw JSON responses without formatting
  --interactive            Force interactive mode even when a command is provided
  --no-interactive         Force non-interactive mode
  --help, -h               Show this help message
`.trim();

export function parseArgs(argv: string[]): ParsedArgs {
  const result: ParsedArgs = {
    interactive: true,
    unknown: []
  };

  const consumeValue = (index: number): string | undefined => {
    const value = argv[index + 1];
    if (value === undefined) {
      return undefined;
    }
    return value;
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];

    switch (arg) {
      case "--url":
      case "-u": {
        const value = consumeValue(i);
        if (value !== undefined) {
          result.url = value;
          i += 1;
        }
        break;
      }
      case "--token-file":
      case "-t": {
        const value = consumeValue(i);
        if (value !== undefined) {
          result.tokenFile = value;
          i += 1;
        }
        break;
      }
      case "--token": {
        const value = consumeValue(i);
        if (value !== undefined) {
          result.token = value;
          i += 1;
        }
        break;
      }
      case "--command": {
        const value = consumeValue(i);
        if (value !== undefined && isCommand(value)) {
          result.command = value;
          result.interactive = false;
          i += 1;
        }
        break;
      }
      case "--tool": {
        const value = consumeValue(i);
        if (value !== undefined) {
          result.tool = value;
          i += 1;
        }
        break;
      }
      case "--args": {
        const value = consumeValue(i);
        if (value !== undefined) {
          result.args = value;
          i += 1;
        }
        break;
      }
      case "--json": {
        result.json = true;
        break;
      }
      case "--interactive": {
        result.interactive = true;
        break;
      }
      case "--no-interactive": {
        result.interactive = false;
        break;
      }
      case "--help":
      case "-h": {
        result.helpRequested = true;
        result.interactive = false;
        break;
      }
      default: {
        if (arg.startsWith("--")) {
          result.unknown.push(arg);
          break;
        }

        if (!result.command && isCommand(arg)) {
          result.command = arg;
          result.interactive = false;
          break;
        }

        if (result.command === "call") {
          if (!result.tool) {
            result.tool = arg;
            break;
          }
          if (!result.args) {
            result.args = arg;
            break;
          }
        }

        result.unknown.push(arg);
      }
    }
  }

  return result;
}

function isCommand(value: string): value is CommandName {
  return COMMANDS.has(value as CommandName);
}
