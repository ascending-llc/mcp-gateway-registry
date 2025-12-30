
export enum SERVER_CONNECTION {
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  CONNECTING = 'connecting',
  ERROR = 'error'
}

export type SERVER_STATUS = {
  connectionState: SERVER_CONNECTION;
  requiresOAuth: boolean;
  error?: string;
}

export type GET_SERVER_STATUS_RESPONSE = {
  success: boolean;
  connectionStatus: {
    [serverName: string]: SERVER_STATUS
  }
}

export type GET_SERVER_AUTH_URL_RESPONSE = {
  success: boolean,
  message: string,
  oauthUrl: string,
  serverName: string,
  oauthRequired: boolean
}

export type CANCEL_AUTH_RESPONSE = {
  success: boolean;
  message: string;
}
