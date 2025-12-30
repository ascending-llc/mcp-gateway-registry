import axios, { type AxiosError, AxiosRequestConfig } from 'axios';

const cancelSources: Record<string, () => void> = {};
const service = axios.create({ baseURL: '/', timeout: 20000 });

type RequestConfig = AxiosRequestConfig & { cancelTokenKey?: string };

service.interceptors.request.use(
  (config: any) => {
    if (config.cancelTokenKey) {
      config.cancelToken = new axios.CancelToken(cancel => {
        cancelSources[config.cancelTokenKey || ''] = cancel;
      });
    }
    
    config.headers = config.headers || {};  
    config.headers['Content-Type'] = 'application/json; charset=utf-8';
    // if (!config.headers.Authorization) config.headers.Authorization = `Bearer ${token}`;

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
    if (axios.isCancel(error)) return { Code: -200, message: '取消请求', cause: '取消请求' };
    return Promise.reject(error);
  },
);

type RequestType = { url: string; method: string; data?: object; config?: AxiosRequestConfig; reTry?: boolean };
const request = async ({ url, method, data = {}, config = {}}: RequestType) => {
  const body = method.toUpperCase() === 'GET' ? { params: data } : { data };
  try {
    const response = await service({ url, method, ...body, ...config });
    return response?.data;
  } catch (error) {
    throw (error as AxiosError).response;
  }
};

const requestGet = (url: string, data?: object, config = {}) => request({ url, data, config, method: 'GET' });
const requestPut = (url: string, data?: object, config = {}) => request({ url, data, config, method: 'PUT' });
const requestPost = (url: string, data?: object, config = {}) => request({ url, data, config, method: 'POST' });
const requestDelete = (url: string, data?: object, config = {}) => request({ url, data, config, method: 'DELETE' });

const Request = {
  get: requestGet,
  put: requestPut,
  post: requestPost,
  delete: requestDelete,
  cancels: cancelSources,
};

export default Request;
