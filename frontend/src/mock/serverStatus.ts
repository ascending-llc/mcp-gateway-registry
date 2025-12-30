import { SERVER_CONNECTION, SERVER_STATUS } from '../services/mcp/type'

export const mockServerStatus: Record<string, SERVER_STATUS> = {
  "ZhipuAI GLM-MCP": {
    connectionState: SERVER_CONNECTION.CONNECTED,
    requiresOAuth: true,
    error: undefined,
  },
  "dsf": {
    connectionState: SERVER_CONNECTION.DISCONNECTED,
    requiresOAuth: true,
    error: undefined,
  },  
  "test_ex": {
    connectionState: SERVER_CONNECTION.CONNECTED,
    requiresOAuth: false,
    error: undefined,
  },
};
