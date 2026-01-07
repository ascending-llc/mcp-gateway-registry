export type GET_TOKEN_REQUEST = {
  expires_in_hours: number;
  description: string;
  scopeMethod?: 'current' | 'custom';
  customScopes?: string;
};

export type GET_TOKEN_RESPONSE = {
  success: boolean;
  tokens: {
    access_token: string;
    refresh_token: string;
    expires_in: number;
    refresh_expires_in: number;
    token_type: string;
    scope: string;
    issued_at: number;
    description: string;
  };
  keycloak_url: string;
  realm: string;
  client_id: string;
  token_data: {
    access_token: string;
    refresh_token: string;
    token_type: string;
    expires_in: number;
    refresh_expires_in: number;
    scope: string;
    issued_at: number;
    description: string;
  };
  user_scopes: string[];
  requested_scopes: string[];
};
