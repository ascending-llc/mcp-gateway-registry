import type {CommandName} from "../parseArgs.js";
import type {JsonRpcResponse} from "../types/mcp.js";
import {executePythonMcpCommand} from "./pythonClient.js";

export interface McpExecutionResult {
  handshake: JsonRpcResponse;
  response: JsonRpcResponse;
}

/**
 * Execute MCP command using the Python client backend.
 *
 * This function bridges the TypeScript CLI to the Python mcp_client.py,
 * eliminating duplicate client implementations while maintaining the Ink UI.
 */
export async function executeMcpCommand(
  command: CommandName,
  gatewayUrl: string,
  gatewayToken?: string,
  backendToken?: string,
  callOptions?: {tool: string; args: Record<string, unknown>}
): Promise<McpExecutionResult> {
  // Delegate to Python client
  return executePythonMcpCommand(
    command,
    gatewayUrl,
    gatewayToken,
    backendToken,
    callOptions
  );
}

export function formatMcpResult(
  command: "ping" | "list" | "init" | "call",
  handshake: JsonRpcResponse,
  response: JsonRpcResponse,
  tool?: string
): string[] {
  const lines: string[] = [];
  const sessionId = (handshake as {result?: {sessionId?: string}}).result?.sessionId;
  if (sessionId) {
    lines.push(`Session established: ${sessionId}`);
  }
  if (command === "ping") {
    lines.push("Ping response:");
    lines.push(JSON.stringify(response, null, 2));
  } else if (command === "list") {
    lines.push("Available tools:");
    lines.push(JSON.stringify(response, null, 2));
  } else if (command === "call") {
    lines.push(`Tool "${tool}" response:`);
    lines.push(JSON.stringify(response, null, 2));
  } else if (command === "init") {
    lines.push("Initialization payload:");
    lines.push(JSON.stringify(handshake, null, 2));
  }
  return lines;
}
