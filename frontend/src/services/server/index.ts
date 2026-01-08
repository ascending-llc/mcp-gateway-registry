import API from '@/services/api';
import Request from '@/services/request';

import type * as TYPE from './type';

const getVersion: () => Promise<TYPE.GET_VERSION_RESPONSE> = async () => await Request.get(API.getVersion);

const getServers: any = async (data?: TYPE.GET_SERVERS_QUERY) => await Request.get(API.getServers, data);

const getServerDetail: any = async (id: string) => await Request.get(API.getServerDetail(id));

const createServer: any = async (data: any) => await Request.post(API.createServer, data);

const updateServer: any = async (id: string, data: any) => await Request.patch(API.updateServer(id), data);

const deleteServer: any = async (id: string) => await Request.delete(API.deleteServer(id));

const toggleServerStatus: any = async (id: string, data: { enabled: boolean }) =>
  await Request.post(API.toggleServerStatus(id), data);

const getServerTools: any = async (id: string) => await Request.get(API.getServerTools(id));

const refreshServerHealth: any = async (id: string) => await Request.post(API.refreshServerHealth(id));

export default {
  getVersion,
  getServers,
  getServerDetail,
  createServer,
  updateServer,
  deleteServer,
  toggleServerStatus,
  getServerTools,
  refreshServerHealth,
};
