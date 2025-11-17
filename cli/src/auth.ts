import {promises as fs} from "node:fs";
import path from "node:path";
import os from "node:os";

export type BackendSource = "none" | "token-file" | "m2m" | "explicit";
export type GatewaySource = "none" | "ingress-json" | "env" | "token-file";

export interface TokenInspection {
  label: string;
  expiresAt?: Date;
  secondsRemaining?: number;
  expired: boolean;
  warning?: string;
}

export interface AuthContext {
  backendToken?: string;
  backendSource: BackendSource;
  gatewayToken?: string;
  gatewaySource: GatewaySource;
  tokenFile?: string;
  warnings: string[];
  inspections: TokenInspection[];
}

export interface ResolveAuthOptions {
  tokenFile?: string;
  explicitToken?: string;
  cwd?: string;
}

const ONE_MINUTE = 60;

export async function resolveAuth(options: ResolveAuthOptions): Promise<AuthContext> {
  const warnings: string[] = [];
  const inspections: TokenInspection[] = [];

  // Use parent directory if running from cli/ subdirectory
  let cwd = options.cwd ?? process.cwd();
  if (cwd.endsWith('/cli') || cwd.endsWith('\\cli')) {
    cwd = path.dirname(cwd);
  }

  let backendToken: string | undefined;
  let backendSource: BackendSource = "none";
  let tokenFile: string | undefined;

  if (options.explicitToken) {
    backendToken = options.explicitToken;
    backendSource = "explicit";
    tokenFile = undefined;
  } else if (options.tokenFile) {
    const loaded = await loadTokenFromPlainFile(options.tokenFile);
    if (loaded) {
      backendToken = loaded;
      backendSource = "token-file";
      tokenFile = options.tokenFile;
    } else {
      warnings.push(`Failed to read token file: ${options.tokenFile}`);
    }
  }

  if (!backendToken) {
    const m2mToken = await fetchM2MToken();
    if (m2mToken?.token) {
      backendToken = m2mToken.token;
      backendSource = "m2m";
      inspections.push(buildInspection("M2M token", backendToken));
      if (m2mToken.warning) {
        warnings.push(m2mToken.warning);
      }
    } else if (m2mToken?.warning) {
      warnings.push(m2mToken.warning);
    }
  } else {
    inspections.push(buildInspection("Backend token", backendToken));
  }

  const gatewayTokenResult = await resolveGatewayToken(cwd);
  let gatewayToken: string | undefined = gatewayTokenResult.token;
  let gatewaySource: GatewaySource = gatewayTokenResult.source;
  if (gatewayToken) {
    inspections.push(buildInspection("Gateway token", gatewayToken));
    if (gatewayTokenResult.warning) {
      warnings.push(gatewayTokenResult.warning);
    }
  }

  // Filter out falsy warnings
  const filteredWarnings = warnings.filter(Boolean);

  return {
    backendToken,
    backendSource,
    gatewayToken,
    gatewaySource,
    tokenFile,
    warnings: filteredWarnings,
    inspections
  };
}

async function loadTokenFromPlainFile(filePath: string): Promise<string | undefined> {
  try {
    const absolutePath = path.resolve(filePath);
    const content = await fs.readFile(absolutePath, "utf-8");
    const token = content.trim();
    return token.length > 0 ? token : undefined;
  } catch {
    return undefined;
  }
}

async function resolveGatewayToken(cwd: string): Promise<{token?: string; source: GatewaySource; warning?: string}> {
  const envToken = process.env.MCP_GATEWAY_TOKEN;
  if (envToken) {
    return {
      token: envToken,
      source: "env"
    };
  }

  const ingressJsonPath = path.join(cwd, ".oauth-tokens", "ingress.json");
  const ingressToken = await loadOAuthTokenFromFile(ingressJsonPath);
  if (ingressToken) {
    const inspection = inspectJwt(ingressToken);
    let warning: string | undefined;
    if (inspection && inspection.expired) {
      warning = `Ingress token in ${ingressJsonPath} is expired`;
    } else if (inspection && inspection.secondsRemaining !== undefined && inspection.secondsRemaining <= ONE_MINUTE) {
      warning = `Ingress token in ${ingressJsonPath} expires in ${inspection.secondsRemaining} seconds`;
    }
    return {
      token: ingressToken,
      source: "ingress-json",
      warning
    };
  }

  const homeIngressPath = path.join(os.homedir(), ".mcp", "ingress_token");
  const fallbackToken = await loadTokenFromPlainFile(homeIngressPath);
  if (fallbackToken) {
    return {
      token: fallbackToken,
      source: "token-file"
    };
  }

  return {
    source: "none"
  };
}

async function loadOAuthTokenFromFile(filePath: string): Promise<string | undefined> {
  try {
    const content = await fs.readFile(filePath, "utf-8");
    const json = JSON.parse(content) as Record<string, unknown>;

    let accessToken: unknown;
    let expiresAt: number | undefined;

    if ("tokens" in json && typeof json.tokens === "object" && json.tokens !== null) {
      const tokens = json.tokens as Record<string, unknown>;
      accessToken = tokens.access_token ?? tokens.token;
      if (typeof tokens.expires_at === "number") {
        expiresAt = tokens.expires_at;
      }
    } else {
      accessToken = json.access_token ?? json.token;
      if (typeof json.expires_at === "number") {
        expiresAt = json.expires_at;
      }
    }

    if (typeof accessToken !== "string") {
      return undefined;
    }

    if (expiresAt && expiresAt <= Date.now() / 1000) {
      return undefined;
    }

    return accessToken;
  } catch {
    return undefined;
  }
}

async function fetchM2MToken(): Promise<{token?: string; warning?: string} | undefined> {
  const clientId = process.env.CLIENT_ID;
  const clientSecret = process.env.CLIENT_SECRET;
  const keycloakUrl = process.env.KEYCLOAK_URL;
  const realm = process.env.KEYCLOAK_REALM;

  if (!clientId || !clientSecret || !keycloakUrl || !realm) {
    return undefined;
  }

  const params = new URLSearchParams();
  params.set("grant_type", "client_credentials");
  params.set("client_id", clientId);
  params.set("client_secret", clientSecret);
  params.set("scope", "openid");

  const tokenUrl = `${keycloakUrl.replace(/\/$/, "")}/realms/${realm}/protocol/openid-connect/token`;

  try {
    const response = await fetch(tokenUrl, {
      method: "POST",
      headers: {
        "content-type": "application/x-www-form-urlencoded"
      },
      body: params.toString()
    });

    if (!response.ok) {
      return {warning: `Failed to obtain M2M token (${response.status} ${response.statusText})`};
    }

    const data = (await response.json()) as Record<string, unknown>;
    const accessToken = data.access_token;
    const expiresIn = typeof data.expires_in === "number" ? data.expires_in : undefined;

    if (typeof accessToken !== "string" || accessToken.length === 0) {
      return {warning: "M2M token response did not include an access_token field"};
    }

    let warning: string | undefined;
    if (expiresIn !== undefined && expiresIn <= ONE_MINUTE) {
      warning = `M2M token expires in ${expiresIn} seconds`;
    }

    return {
      token: accessToken,
      warning
    };
  } catch (error) {
    return {warning: `Failed to fetch M2M token: ${(error as Error).message}`};
  }
}

function buildInspection(label: string, token: string): TokenInspection {
  const inspection = inspectJwt(token);
  if (!inspection) {
    return {
      label,
      expired: false
    };
  }

  const warning = inspection.warning ?? (inspection.secondsRemaining !== undefined && inspection.secondsRemaining <= ONE_MINUTE
    ? `${label} expires in ${inspection.secondsRemaining} seconds`
    : undefined);

  return {
    label,
    expiresAt: inspection.expiresAt,
    secondsRemaining: inspection.secondsRemaining,
    expired: inspection.expired,
    warning
  };
}

function inspectJwt(token: string): {
  expiresAt?: Date;
  secondsRemaining?: number;
  expired: boolean;
  warning?: string;
} | undefined {
  const parts = token.split(".");
  if (parts.length !== 3) {
    return {
      expired: false,
      warning: "Token is not a valid JWT format"
    };
  }

  try {
    const payload = JSON.parse(base64UrlDecode(parts[1])) as Record<string, unknown>;
    if (typeof payload.exp !== "number") {
      return {
        expired: false,
        warning: "Token does not declare an expiration time"
      };
    }
    const expiresAt = new Date(payload.exp * 1000);
    const secondsRemaining = Math.floor(payload.exp - Date.now() / 1000);
    return {
      expiresAt,
      secondsRemaining,
      expired: secondsRemaining <= 0
    };
  } catch {
    return {
      expired: false,
      warning: "Token payload could not be decoded"
    };
  }
}

function base64UrlDecode(segment: string): string {
  const normalized = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padding = normalized.length % 4;
  const padded = padding === 0 ? normalized : normalized + "=".repeat(4 - padding);
  const buffer = Buffer.from(padded, "base64");
  return buffer.toString("utf-8");
}
