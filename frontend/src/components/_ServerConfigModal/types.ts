export type AuthType = 'auto' | 'api-key' | 'oauth';
export type ApiKeySource = 'global' | 'user';
export type ApiKeyHeaderFormat = 'bearer' | 'basic' | 'custom';
export type ServerType = 'streamable-https' | 'sse';

export interface AuthenticationConfig {
  type: AuthType;
  // API Key specific props
  apiKeySource?: ApiKeySource;
  apiKey?: string;
  headerFormat?: ApiKeyHeaderFormat;
  // OAuth specific props
  clientId?: string;
  clientSecret?: string;
  authorizationUrl?: string;
  tokenUrl?: string;
  scope?: string;
}

export interface ServerConfig {
  icon?: string; // URL or base64
  name: string;
  description: string;
  url: string;
  serverType: ServerType;
  authConfig: AuthenticationConfig;
  trustServer: boolean;
}
