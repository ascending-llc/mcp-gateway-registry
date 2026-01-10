import API from '@/services/api';
import Request from '@/services/request';

import type * as TYPE from './type';

const getServerStatus: () => Promise<TYPE.GET_SERVER_STATUS_RESPONSE> = async () =>
  await Request.get(API.getServerStatus);

const getOauthInitiate: (name: string) => Promise<TYPE.GET_OAUTH_INITIATE_RESPONSE> = async name =>
  await Request.get(API.getOauthInitiate(name));

const getSOauthReinit: (name: string) => Promise<TYPE.GET_SERVER_AUTH_URL_RESPONSE> = async name =>
  await Request.post(API.getSOauthReinit(name));

const cancelAuth: (name: string) => Promise<TYPE.CANCEL_AUTH_RESPONSE> = async name =>
  await Request.post(API.cancelAuth(name));

export default {
  getServerStatus,
  getOauthInitiate,
  getSOauthReinit,
  cancelAuth,
};
