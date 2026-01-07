const SERVER_BASE_URL = '/api/v1';

const API = {
  getToken: '/api/tokens/generate',

  getVersion: '/api/version',

  getServers: `${SERVER_BASE_URL}/servers`,
  getServerDetail: (id: string) => `${SERVER_BASE_URL}/servers/${id}`,
  createServer: `${SERVER_BASE_URL}/servers`,
  updateServer: (id: string) => `${SERVER_BASE_URL}/servers/${id}`,
  deleteServer: (id: string) => `${SERVER_BASE_URL}/servers/${id}`,
  toggleServerStatus: (id: string) => `${SERVER_BASE_URL}/servers/${id}/toggle`,
  getServerTools: (id: string) => `${SERVER_BASE_URL}/servers/${id}/tools`,
  refreshServerHealth: (id: string) => `${SERVER_BASE_URL}/servers/${id}/refresh`,
};

export default API;
