import API from '@/services/api';
import Request from '@/services/request';

import type * as TYPE from './type';

const getServerStatus: () => Promise<TYPE.GET_SERVER_STATUS_RESPONSE> = async () =>
  await Request.get(API.getServerStatus);

const getServerAuthUrl: (name: string) => Promise<TYPE.GET_SERVER_AUTH_URL_RESPONSE> = async name =>
  await Request.post(API.getServerAuthUrl(name));

const cancelAuth: (name: string) => Promise<TYPE.CANCEL_AUTH_RESPONSE> = async name =>
  await Request.post(API.cancelAuth(name));

export default {
  getServerStatus,
  getServerAuthUrl,
  cancelAuth,
};
