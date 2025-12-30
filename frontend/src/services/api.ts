const API = {
  getServerStatus: '/api/mcp/connection/status',
  getServerAuthUrl: (macName: string) => `/api/mcp/${macName}/reinitialize`,
  cancelAuth: (serverName: string) => `/api/mcp/oauth/cancel/${serverName}`,
};

export default API;
