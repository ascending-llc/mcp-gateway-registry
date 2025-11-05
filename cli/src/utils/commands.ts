/**
 * Available slash commands for autocomplete
 */

export interface CommandOption {
  command: string;
  description: string;
  category: string;
}

export const AVAILABLE_COMMANDS: CommandOption[] = [
  // Essential commands only - focus on natural language interaction
  { command: "/help", description: "Show help message", category: "Basic" },
  { command: "/exit", description: "Exit the CLI", category: "Basic" },
  { command: "/ping", description: "Test gateway connectivity", category: "Basic" },
  { command: "/list", description: "List available tools", category: "Basic" },
  { command: "/servers", description: "List all MCP servers", category: "Basic" },
];

/**
 * Get command suggestions based on partial input
 */
export function getCommandSuggestions(input: string): CommandOption[] {
  if (!input.startsWith("/")) {
    return [];
  }

  const normalized = input.toLowerCase();

  return AVAILABLE_COMMANDS.filter(cmd =>
    cmd.command.toLowerCase().startsWith(normalized)
  ).slice(0, 10); // Limit to 10 suggestions
}

/**
 * Get all commands for a specific category
 */
export function getCommandsByCategory(category: string): CommandOption[] {
  return AVAILABLE_COMMANDS.filter(cmd => cmd.category === category);
}
