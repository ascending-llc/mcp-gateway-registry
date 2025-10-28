import type {TaskCategory} from "../tasks/types.js";

export type CommandKind = "help" | "ping" | "list" | "servers" | "init" | "call" | "task" | "exit" | "unknown";

export interface BaseParsedCommand {
  kind: CommandKind;
}

export interface HelpCommand extends BaseParsedCommand {
  kind: "help";
}

export interface ExitCommand extends BaseParsedCommand {
  kind: "exit";
}

export interface PingCommand extends BaseParsedCommand {
  kind: "ping" | "list" | "servers" | "init";
}

export interface CallCommand extends BaseParsedCommand {
  kind: "call";
  tool?: string;
  argsJson?: string;
  rawTokens: string[];
}

export interface TaskCommand extends BaseParsedCommand {
  kind: "task";
  category: TaskCategory;
  subcommand: string;
  tokens: string[];
}

export interface UnknownCommand extends BaseParsedCommand {
  kind: "unknown";
  message: string;
}

export type ParsedCommand = HelpCommand | ExitCommand | PingCommand | CallCommand | TaskCommand | UnknownCommand;

const TASK_PREFIXES: Record<string, TaskCategory> = {
  service: "service",
  services: "service",
  svc: "service",
  import: "import",
  imports: "import",
  registry: "import",
  user: "user",
  users: "user",
  diagnostic: "diagnostic",
  diagnostics: "diagnostic",
  diag: "diagnostic"
};

const SIMPLE_COMMANDS: Record<string, PingCommand["kind"]> = {
  ping: "ping",
  list: "list",
  tools: "list",
  servers: "servers",
  init: "init",
  initialize: "init"
};

export function parseCommand(input: string): ParsedCommand {
  const trimmed = input.trim();
  const withoutSlash = trimmed.startsWith("/") ? trimmed.slice(1).trim() : trimmed;
  if (!withoutSlash) {
    return {kind: "help"};
  }

  const tokens = tokenize(withoutSlash);
  if (tokens.length === 0) {
    return {kind: "help"};
  }

  const keyword = tokens.shift()!.toLowerCase();

  if (keyword === "help" || keyword === "?") {
    return {kind: "help"};
  }

  if (keyword === "exit" || keyword === "quit" || keyword === "q") {
    return {kind: "exit"};
  }

  if (keyword === "call") {
    return parseCall(tokens);
  }

  const simpleKind = SIMPLE_COMMANDS[keyword];
  if (simpleKind) {
    return {kind: simpleKind};
  }

  const category = TASK_PREFIXES[keyword];
  if (category) {
    if (tokens.length === 0) {
      return {
        kind: "unknown",
        message: `I need a subcommand for ${category} tasks. Try "/${category} help" or "/help".`
      };
    }

    const subcommand = tokens.shift()!.toLowerCase();

    if (subcommand === "help") {
      return {
        kind: "unknown",
        message: describeCategory(category)
      };
    }

    return {
      kind: "task",
      category,
      subcommand,
      tokens
    };
  }

  return {
    kind: "unknown",
    message: `I don't recognise the command "${keyword}". Try "/help" to see what I can do.`
  };
}

function parseCall(tokens: string[]): CallCommand {
  let tool: string | undefined;
  let argsJson: string | undefined;

  if (tokens.length > 0 && !tokens[0].includes("=")) {
    tool = tokens.shift();
  }

  for (const token of tokens) {
    const [key, value] = splitToken(token);
    if (!key || value === undefined) {
      continue;
    }
    if (key === "tool" && !tool) {
      tool = value;
    }
    if (key === "args" || key === "json") {
      argsJson = value;
    }
  }

  return {
    kind: "call",
    tool,
    argsJson,
    rawTokens: tokens
  };
}

function describeCategory(category: TaskCategory): string {
  switch (category) {
    case "service":
      return "Service toolkit commands: /service add, /service delete, /service monitor, /service test, /service add-groups, /service remove-groups, /service create-group, /service delete-group, /service list-groups.";
    case "import":
      return "Registry import commands: /import dry, /import apply (optional import-list=<file>).";
    case "user":
      return "User management commands: /user create-m2m, /user create-human, /user delete, /user list, /user list-groups.";
    case "diagnostic":
      return "Diagnostics commands: /diagnostic run-suite, /diagnostic run-test.";
    default:
      return "Unknown category.";
  }
}

export function tokenize(text: string): string[] {
  const tokens: string[] = [];
  const regex = /"([^"\\]*(\\.[^"\\]*)*)"|'([^'\\]*(\\.[^'\\]*)*)'|[^\s]+/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    const token = match[0];
    tokens.push(unquote(token));
  }
  return tokens;
}

function unquote(token: string): string {
  if (token.length >= 2) {
    const first = token[0];
    const last = token[token.length - 1];
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      const inner = token.slice(1, -1);
      return inner.replace(/\\(["'\\])/g, "$1").replace(/\\n/g, "\n").replace(/\\t/g, "\t");
    }
  }
  return token;
}

export function splitToken(token: string): [string | undefined, string | undefined] {
  const index = token.indexOf("=");
  if (index === -1) {
    return [undefined, token];
  }
  const key = token.slice(0, index).toLowerCase();
  const value = token.slice(index + 1);
  return [key, value];
}
