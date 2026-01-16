import API from '@/services/api';
import Request from '@/services/request';

import type * as TOKEN_TYPE from './type';

const getAuthMe: () => Promise<TOKEN_TYPE.GET_AUTH_ME_RESPONSE> = async () => await Request.get(API.getAuthMe);

const getToken: (data: TOKEN_TYPE.GET_TOKEN_REQUEST) => Promise<TOKEN_TYPE.GET_TOKEN_RESPONSE> = async data =>
  await Request.post(API.getToken, data, { skipTokenBarrier: true });

export default {
  getAuthMe,
  getToken,
};
