import API from '@/services/api';
import Request from '@/services/request';

import type * as TYPE from './type';

const getVersion: () => Promise<TYPE.GET_VERSION_RESPONSE> = async () => await Request.get(API.getVersion);

const getServers: (data?: TYPE.GET_SERVERS_REQUEST) => Promise<TYPE.GET_SERVERS_RESPONSE> = async data =>
  await Request.get(API.getServers, data);

const getServerDetail: (id: string) => Promise<TYPE.GET_SERVERS_DETAIL_RESPONSE> = async id =>
  await Request.get(API.getServerDetail(id));

const createServer: (data: TYPE.CREATE_SERVER_REQUEST) => Promise<TYPE.Server> = async data =>
  await Request.post(API.createServer, data);

const updateServer: (id: string, data: Partial<TYPE.Server>) => Promise<TYPE.Server> = async (id, data) =>
  await Request.patch(API.updateServer(id), data);

const deleteServer: (id: string) => Promise<void> = async id => await Request.delete(API.deleteServer(id));

const toggleServerStatus: (id: string, data: { enabled: boolean }) => Promise<void> = async (id, data) =>
  await Request.post(API.toggleServerStatus(id), data);

const getServerTools: (id: string) => Promise<TYPE.GET_SERVER_TOOLS_RESPONSE> = async id =>
  await Request.get(API.getServerTools(id));

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
