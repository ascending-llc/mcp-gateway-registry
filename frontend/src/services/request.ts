import axios, { type AxiosError, type AxiosRequestConfig } from 'axios';

import { getBasePath } from '@/config';
import UTILS from '@/utils';
import type { GET_TOKEN_RESPONSE } from './auth/type';

const cancelSources: Record<string, () => void> = {};
const service = axios.create({ baseURL: getBasePath() || '/', timeout: 20000 });

type RequestConfig = AxiosRequestConfig & { cancelTokenKey?: string; skipTokenBarrier?: boolean };

let tokenInitPromise: Promise<GET_TOKEN_RESPONSE> | null = null;

export const setTokenInitPromise = (promise: Promise<GET_TOKEN_RESPONSE> | null) => {
  tokenInitPromise = promise;
};

service.interceptors.request.use(
  async (config: any) => {
    if (!config.skipTokenBarrier && tokenInitPromise) {
      await tokenInitPromise;
    }

    if (config.cancelTokenKey) {
      config.cancelToken = new axios.CancelToken(cancel => {
        cancelSources[config.cancelTokenKey || ''] = cancel;
      });
    }

    config.headers = config.headers || {};
    config.headers['Content-Type'] = 'application/json; charset=utf-8';
    if (!config.headers.Authorization) {
      const token = UTILS.getSessionConfig('accessToken');
      if (token) config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  error => {
    return Promise.reject(error);
  },
);

service.interceptors.response.use(
  response => {
    const key = (response?.config as RequestConfig)?.cancelTokenKey || '';
    if (key && cancelSources[key]) delete cancelSources[key];
    return response;
  },
  (error: AxiosError) => {
    if (axios.isCancel(error)) return { Code: -200, message: 'Cancel request', cause: 'Cancel request' };
    return Promise.reject(error);
  },
);

type RequestType = { url: string; method: string; data?: object; config?: AxiosRequestConfig; reTry?: boolean };
const request = async ({ url, method, data = {}, config = {} }: RequestType) => {
  const body = method.toUpperCase() === 'GET' ? { params: data } : { data };
  try {
    const response = await service({ url, method, ...body, ...config });
    return response?.data;
  } catch (error) {
    throw (error as AxiosError).response?.data;
  }
};

const requestGet = (url: string, data?: object, config = {}) => request({ url, data, config, method: 'GET' });
const requestPut = (url: string, data?: object, config = {}) => request({ url, data, config, method: 'PUT' });
const requestPost = (url: string, data?: object, config = {}) => request({ url, data, config, method: 'POST' });
const requestPatch = (url: string, data?: object, config = {}) => request({ url, data, config, method: 'PATCH' });
const requestDelete = (url: string, data?: object, config = {}) => request({ url, data, config, method: 'DELETE' });

const Request = {
  get: requestGet,
  put: requestPut,
  post: requestPost,
  patch: requestPatch,
  delete: requestDelete,
  cancels: cancelSources,
};

export default Request;
