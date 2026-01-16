const BASE_URL = '/api/v1';
const MCP_BASE_URL = `${BASE_URL}/mcp`;
const SERVER_BASE_URL = `${BASE_URL}/servers`;

const API = {
  // auth
  getAuthMe: '/api/auth/me',
  getToken: '/api/tokens/generate',

  getVersion: '/api/version',

  // mcp
  getServerStatus: `${MCP_BASE_URL}/connection/status`,
  getOauthInitiate: (name: string) => `${MCP_BASE_URL}/${name}/oauth/initiate`,
  getSOauthReinit: (name: string) => `${MCP_BASE_URL}/${name}/reinitialize`,
  cancelAuth: (name: string) => `${MCP_BASE_URL}/oauth/cancel/${name}`,

  // server
  getServers: `${SERVER_BASE_URL}`,
  getServerDetail: (id: string) => `${SERVER_BASE_URL}/${id}`,
  createServer: `${SERVER_BASE_URL}`,
  updateServer: (id: string) => `${SERVER_BASE_URL}/${id}`,
  deleteServer: (id: string) => `${SERVER_BASE_URL}/${id}`,
  toggleServerStatus: (id: string) => `${SERVER_BASE_URL}/${id}/toggle`,
  getServerTools: (id: string) => `${SERVER_BASE_URL}/${id}/tools`,
  refreshServerHealth: (id: string) => `${SERVER_BASE_URL}/${id}/refresh`,
};

export default API;
