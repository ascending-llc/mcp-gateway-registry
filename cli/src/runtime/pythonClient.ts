import {spawn, type ChildProcess} from "child_process";
import {resolve, join, dirname} from "path";
import {writeFileSync, unlinkSync, mkdtempSync} from "fs";
import {tmpdir} from "os";
import {fileURLToPath} from "url";
import type {JsonRpcResponse} from "../types/mcp.js";

// ES module compatibility for __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export interface PythonMcpExecutionResult {
  handshake: JsonRpcResponse;
  response: JsonRpcResponse;
}

/**
 * Execute Python MCP client command
 *
 * This bridges the TypeScript CLI to the Python mcp_client.py,
 * eliminating duplicate client code while maintaining the Ink UI.
 */
export async function executePythonMcpCommand(
  command: "ping" | "list" | "init" | "call",
  gatewayUrl: string,
  gatewayToken?: string,
  backendToken?: string,
  callOptions?: {tool: string; args: Record<string, unknown>}
): Promise<PythonMcpExecutionResult> {
  // Build Python command arguments
  const pythonScript = resolve(__dirname, "../../mcp_client.py");
  const args = ["--url", gatewayUrl];

  let tokenFile: string | undefined;

  // Add authentication if available
  // Priority: gatewayToken (for MCP gateway) > backendToken (for specific servers)
  const tokenToUse = gatewayToken || backendToken;
  if (tokenToUse) {
    // Use a temporary file to pass the token
    // Write ONLY the token string (not JSON) as Python client expects plain token
    const tmpDir = mkdtempSync(join(tmpdir(), "mcp-token-"));
    tokenFile = join(tmpDir, ".mcp_token");

    try {
      // Ensure we write just the token string, not any JSON wrapper
      const tokenString = tokenToUse.trim();
      writeFileSync(tokenFile, tokenString);
      args.push("--token-file", tokenFile);
    } catch (error) {
      // Clean up temp file
      try {
        if (tokenFile) {
          unlinkSync(tokenFile);
        }
      } catch {
        // Ignore cleanup errors
      }
      throw error;
    }
  }

  // Add command
  args.push(command);

  // Add tool call parameters if needed
  if (command === "call" && callOptions) {
    args.push("--tool", callOptions.tool);
    if (callOptions.args && Object.keys(callOptions.args).length > 0) {
      args.push("--args", JSON.stringify(callOptions.args));
    }
  }

  // Execute Python script
  return new Promise((promiseResolve, promiseReject) => {
    let stdout = "";
    let stderr = "";

    // Use uv run to execute the Python script
    const proc: ChildProcess = spawn("uv", ["run", pythonScript, ...args], {
      cwd: resolve(__dirname, "../.."),
      env: process.env
    });

    if (proc.stdout) {
      proc.stdout.on("data", (data: Buffer) => {
        stdout += data.toString();
      });
    }

    if (proc.stderr) {
      proc.stderr.on("data", (data: Buffer) => {
        stderr += data.toString();
      });
    }

    proc.on("error", (error: Error) => {
      // Clean up temp file
      if (tokenFile) {
        try {
          unlinkSync(tokenFile);
        } catch {
          // Ignore cleanup errors
        }
      }
      promiseReject(new Error(`Failed to execute Python client: ${error.message}`));
    });

    proc.on("close", (code: number | null) => {
      // Clean up temp file
      if (tokenFile) {
        try {
          unlinkSync(tokenFile);
        } catch {
          // Ignore cleanup errors
        }
      }

      if (code !== 0) {
        promiseReject(new Error(`Python client exited with code ${code}: ${stderr}`));
        return;
      }

      try {
        // Parse the JSON output from Python client
        const lines = stdout.trim().split("\n");

        // Find the JSON response (skip authentication success messages)
        // The JSON may span multiple lines, so we need to collect all lines from the first { to the last }
        let jsonStartIndex = -1;
        let jsonEndIndex = -1;

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          if (jsonStartIndex === -1 && (line.startsWith("{") || line.startsWith("["))) {
            jsonStartIndex = i;
          }
          if (jsonStartIndex !== -1 && (line.endsWith("}") || line.endsWith("]"))) {
            jsonEndIndex = i;
            // Continue to find the last closing brace
          }
        }

        if (jsonStartIndex === -1 || jsonEndIndex === -1) {
          promiseReject(new Error(`No JSON output from Python client: ${stdout}`));
          return;
        }

        // Collect all lines from start to end of JSON
        const jsonOutput = lines.slice(jsonStartIndex, jsonEndIndex + 1).join("\n");

        const result = JSON.parse(jsonOutput);

        // Transform Python response to match TypeScript interface
        let handshake: JsonRpcResponse;
        let response: JsonRpcResponse;

        if (command === "init") {
          // For init, both are the same
          handshake = result;
          response = result;
        } else {
          // For other commands, create a basic handshake response
          handshake = {
            jsonrpc: "2.0",
            result: {
              protocolVersion: "2024-11-05",
              capabilities: {},
              serverInfo: {
                name: "mcp-gateway",
                version: "1.0.0"
              }
            }
          };
          response = result;
        }

        promiseResolve({handshake, response});
      } catch (error) {
        promiseReject(new Error(`Failed to parse Python client output: ${(error as Error).message}\nOutput: ${stdout}`));
      }
    });
  });
}
