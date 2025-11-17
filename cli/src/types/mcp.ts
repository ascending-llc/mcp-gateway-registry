/**
 * MCP Protocol Type Definitions
 *
 * These types define the JSON-RPC 2.0 interface used by the Model Context Protocol (MCP).
 * They are shared between the Python client bridge and the rest of the TypeScript CLI.
 */

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: number;
  method: string;
  params?: Record<string, unknown>;
}

export interface JsonRpcResponse<T = unknown> {
  jsonrpc: "2.0";
  result?: T;
  error?: unknown;
  id?: number | string;
}

export type ToolArguments = Record<string, unknown>;
