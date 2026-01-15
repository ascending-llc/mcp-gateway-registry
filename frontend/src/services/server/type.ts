import type { ApiKeyHeaderFormat, ApiKeySource, ServerType } from '@/components/ServerFormDialog/types';
import type { SERVER_CONNECTION } from '@/services/mcp/type';

export type GET_VERSION_RESPONSE = {
  version: string;
};

export type GET_SERVERS_REQUEST = {
  query?: string;
  scope?: string;
  status?: string;
  page?: string;
  per_page?: string;
};

export type OauthConfig = {
  authorization_url: string;
  token_url: string;
  client_id: string;
  client_secret: string;
  scope: string;
};
export type ApiKeyConfig = {
  key: string;
  source: ApiKeySource;
  authorization_type: ApiKeyHeaderFormat;
  custom_header: string;
};
export type StatusType = 'active' | 'inactive' | 'error';
export type Server = {
  id: string;
  serverName: string;
  description: string;
  type: ServerType;
  url: string;
  enabled: boolean;
  requiresOAuth: boolean;
  connection_state: SERVER_CONNECTION;
  capabilities: string;
  tools: string;
  author: string;
  scope: string;
  status: StatusType;
  path: string;
  tags: string[];
  numTools: number;
  numStars: number;
  initDuration: number;
  lastConnected: string;
  createdAt: string;
  updatedAt: string;
  is_python?: boolean;
  is_official?: boolean;
  oauth?: OauthConfig;
  apiKey?: ApiKeyConfig;
};

export type GET_SERVERS_RESPONSE = {
  servers: Server[];
  pagination: {
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
  };
};

export type GET_SERVERS_DETAIL_RESPONSE = {} & Server;

export type CREATE_SERVER_REQUEST = {
  serverName: string;
  description: string;
  path: string;
  url: string;
  tags?: string[];
  enabled: boolean;
  type: ServerType;
  oauth?: OauthConfig;
  apiKey?: ApiKeyConfig;
};

export type Tool = {
  name: string;
  description?: string;
  inputSchema?: any;
};
export type GET_SERVER_TOOLS_RESPONSE = {
  id: string;
  tools: Tool[];
};
