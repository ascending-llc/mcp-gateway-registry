export type AuthType = 'auto' | 'apiKey' | 'oauth';
export type ApiKeySource = 'admin' | 'user';
export type ApiKeyHeaderFormat = 'bearer' | 'basic' | 'custom';
export type ServerType = 'streamable-http' | 'sse';

export interface AuthenticationConfig {
  type: AuthType;
  // API Key specific props
  source?: ApiKeySource;
  key?: string;
  auth_type?: ApiKeyHeaderFormat;
  custom_header?: string;
  // OAuth specific props
  client_id?: string;
  client_secret?: string;
  authorize_url?: string;
  token_url?: string;
  scope?: string;
}

export interface ServerConfig {
  serverName: string;
  description: string;
  path: string;
  url: string;
  supported_transports: ServerType;
  authConfig: AuthenticationConfig;
  trustServer: boolean;
  tags?: string[];
}
