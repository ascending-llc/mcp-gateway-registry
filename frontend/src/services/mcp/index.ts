import API from '../api';
import Request from '../request';

import * as MCP_TYPE from './type'

const getServerStatus: () => Promise<MCP_TYPE.GET_SERVER_STATUS_RESPONSE> = async () => await Request.get(API.getServerStatus);

const getServerAuthUrl: (macName: string) => Promise<MCP_TYPE.GET_SERVER_AUTH_URL_RESPONSE> = async (macName) => await Request.post(API.getServerAuthUrl(macName));

const cancelAuth: (serverName: string) => Promise<MCP_TYPE.CANCEL_AUTH_RESPONSE> = async (serverName) => await Request.post(API.cancelAuth(serverName));

export default {
    getServerStatus,
    getServerAuthUrl,
    cancelAuth
}