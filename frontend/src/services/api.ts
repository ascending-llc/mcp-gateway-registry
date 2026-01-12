const SERVER_BASE_URL = '/api/v1';
const MCP_BASE_URL = '/api/mcp/v1';

const API = {
  getToken: '/api/tokens/generate',

  getVersion: '/api/version',

  // server
  getServers: `${SERVER_BASE_URL}/servers`,
  getServerDetail: (id: string) => `${SERVER_BASE_URL}/servers/${id}`,
  createServer: `${SERVER_BASE_URL}/servers`,
  updateServer: (id: string) => `${SERVER_BASE_URL}/servers/${id}`,
  deleteServer: (id: string) => `${SERVER_BASE_URL}/servers/${id}`,
  toggleServerStatus: (id: string) => `${SERVER_BASE_URL}/servers/${id}/toggle`,
  getServerTools: (id: string) => `${SERVER_BASE_URL}/servers/${id}/tools`,
  refreshServerHealth: (id: string) => `${SERVER_BASE_URL}/servers/${id}/refresh`,

  // auth
  getServerStatus: `${MCP_BASE_URL}/connection/status`,
  getOauthInitiate: (name: string) => `${MCP_BASE_URL}/${name}/oauth/initiate`,
  getSOauthReinit: (name: string) => `${MCP_BASE_URL}/${name}/reinitialize`,
  cancelAuth: (name: string) => `${MCP_BASE_URL}/oauth/cancel/${name}`,
};

export default API;
