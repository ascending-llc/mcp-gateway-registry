# Authentication and Authorization Enhancements for MCP

Authorization in context of MCP usually refers to two distinct flows or grant types:

- Agent acting on-behalf of a user: in this case the Agent takes the identity of the end-user (human). For example, an Agent invoked by an application as a result of a user asking a question in a chatbot will use the user's identity for authentication and authorization.

- Agent acting on its own behalf: in this case the Agent gets invoked automatically in response to an event and thus the Agent has its own identity. For example a network remediation agent that gets invoked when a network anomaly is detected will have an identity of its own as it is not being invoked by a user.

The latest MCP authorization spec available [here](https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization) discusses this in context of OAuth Grant types.

## The challenge with MCP auth in an enterprise scenario

The current MCP spec puts the onus of authentication on the MCP server i.e. the server is responsible for providing access credentials to the MCP client as well as validating those credentials (see [OAuth for model context protocol](https://aaronparecki.com/2025/04/03/15/oauth-for-model-context-protocol) for an illustrative explanation). This implies that developers now have to add Auth capabilities in their MCP servers and in an enterprise scenario with hundreds of MCP servers and thousands of tools this is a huge challenge. The problem is compounded by the fact that enterprises would want to offer fine-grained access controls to tools (an Agent can access the server but only a subset of the tools provided by the server) for both the types of Agent flows described above.

## A Solution with an MCP Gateway and Registry

The MCP gateway and Registry provides an enterprise ready solution that integrates with an IdP and provides a separate auth server which handles all authorization and authentication by talking to an IdP and this frees up the MCP servers from having to handle any authentication.

Here is an architecture diagram of the system.

```mermaid
graph LR
    %% AI Agent
    Agent[AI Agent]
    
    %% CLI Auth Tool
    CLIAuth[CLI Auth Tool<br/>cli_auth.py]
    
    %% Identity Provider
    IdP[Identity Provider]
    
    %% Gateway and Registry Block
    subgraph GwReg["Gateway & Registry"]
        Gateway["Gateway<br/>(Reverse Proxy)"]
        Registry[Registry]
        AuthServer["Auth Server<br/>(Dual Auth)"]
    end
    
    %% MCP Server Farm
    subgraph MCPFarm["MCP Server Farm"]
        MCP1[MCP Server 1]
        MCP2[MCP Server 2]
        MCP3[MCP Server 3]
        MCPn[MCP Server n]
    end
    
    %% Connections
    Agent -->|Discover servers/tools| Registry
    Agent -->|Data plane requests| Gateway
    Gateway -->|Auth verification| AuthServer
    Gateway -->|Proxy requests| MCP1
    Gateway -->|Proxy requests| MCP2
    Gateway -->|Proxy requests| MCP3
    Gateway -->|Proxy requests| MCPn
    
    %% Auth flow
    IdP -.->|M2M: JWT tokens| Agent
    IdP -.->|User: OAuth flow| CLIAuth
    CLIAuth -.->|Session cookie| Agent
    AuthServer -.->|Validate tokens/cookies| IdP
    
    %% Styling
    classDef agentStyle fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef idpStyle fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef gwregStyle fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef mcpStyle fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    classDef cliStyle fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    
    class Agent agentStyle
    class IdP idpStyle
    class Gateway,Registry,AuthServer gwregStyle
    class MCP1,MCP2,MCP3,MCPn mcpStyle
    class CLIAuth cliStyle
```

At a high-level the flow works as follows:

```mermaid
sequenceDiagram
    participant User
    participant Agent as Agent<br/>(includes MCP client)
    participant IdP as Enterprise IdP
    
    box rgba(0,0,0,0) MCP Gateway & Registry Solution
        participant Gateway as Gateway<br/>(Reverse Proxy)
        participant AuthServer as Auth Server
        participant Registry as Registry<br/>MCP Server
    end
    
    participant MCP as External<br/>MCP Server

    %% Step 1: Get credentials
    Note over User,IdP: Step 1: Credential Acquisition (Choose One)
    alt M2M Authentication (Agent Identity)
        Agent->>IdP: Request auth credentials (client_id/secret)
        IdP->>Agent: Return JWT token + scopes
    else Session Cookie (On-behalf of User)
        participant CLIAuth as CLI Auth Tool
        User->>CLIAuth: Run cli_auth.py
        CLIAuth->>IdP: OAuth PKCE flow
        IdP->>CLIAuth: Auth code + user info
        CLIAuth->>CLIAuth: Create session cookie
        CLIAuth->>User: Save to ~/.mcp/session_cookie
        User->>Agent: Provide cookie file path
    end

    %% Step 2: Embed credentials in headers
    Note over Agent: Step 2: Embed credentials + IdP metadata
    alt M2M Headers
        Note over Agent: Authorization: Bearer {JWT}<br/>X-User-Pool-Id: {pool_id}<br/>X-Client-Id: {client_id}<br/>X-Region: {region}
    else Session Cookie Headers
        Note over Agent: Cookie: mcp_gateway_session={cookie}<br/>X-User-Pool-Id: {pool_id}<br/>X-Client-Id: {client_id}<br/>X-Region: {region}
    end

    %% Step 3: Tool Discovery with scoped access
    Note over Agent,Registry: Step 3: Scoped Tool Discovery
    Agent->>Gateway: Tool discovery request with auth headers
    Gateway->>AuthServer: Validate credentials
    alt JWT Token Validation
        AuthServer->>IdP: Verify JWT signature + claims
        IdP->>AuthServer: Token valid + scopes from token
    else Session Cookie Validation
        AuthServer->>AuthServer: Decode cookie with SECRET_KEY
        AuthServer->>AuthServer: Map user groups to scopes
    end
    AuthServer->>Gateway: 200 OK + allowed scopes
    Gateway->>Registry: Tool discovery request + scope headers
    
    Note over Registry: Registry filters tools based<br/>on Agent's allowed scopes
    Registry->>Gateway: Filtered tool list (only accessible tools)
    Gateway->>Agent: Available tools response

    %% Step 4: MCP Tool Invocation to External Server
    Note over Agent,MCP: Step 4: MCP Tool Invocation Flow
    Agent->>Gateway: MCP tool call request with auth headers
    Gateway->>AuthServer: Validate credentials + scope
    AuthServer->>IdP: Verify credentials
    IdP->>AuthServer: Auth response + scope
    
    alt Valid credentials + sufficient scope
        AuthServer->>Gateway: 200 OK + allowed scopes
        Gateway->>MCP: Forward MCP request
        MCP->>Gateway: MCP response
        Gateway->>Agent: MCP response
    else Invalid or insufficient access
        AuthServer->>Gateway: 403 Access Denied
        Gateway->>Agent: 403 Access Denied
    end

    %% Footnotes
    Note over Agent,MCP: Notes:<br/>• Agent can skip tool discovery and call MCP methods directly<br/>• Auth validation flow remains the same for all MCP operations<br/>  (initialize, tools/call with tool-specific scope validation)
```

1. An Agent gets auth credentials from an enterprise IdP either by itself (agent identity) or is provided these credentials (on-behalf of user's identity) that have been retrieved by the (human) user through a separate program (such as signing-in via a web browser or a CLI command).

1. The Agent embeds these credentials and other metadata needed to verify these credentials in HTTP headers for the MCP protocol messages exchanged with the MCP servers.

1. The MCP servers are only accessible through the Gateway (reverse proxy), upon receiving the messages the Gateway hands them off to an auth server which validates the credentials embedded in the these messages with the enterprise IdP. This validation includes both authentication as well as authorization. The auth server retrieves the access scope for the Agent from the IdP auth validation response and then compares it with the MCP method (`initialize`, `tools/call` etc.) and tool being requested. The auth server responds with a 200 OK if the access should be allowed based on the credentials provided and the scope requested or a an HTTP 403 access denied otherwise. The auth server also includes the list of allowed scopes in its 200 OK response.

1. The Gateway then proceeds to pass on the request to the MCP server to which the request was addressed to in case the access was allowed (200 OK from the auth server) or sends the 403 access denied to the Agent. 

1. An Agent uses the same mechanism to talk to the Registry's MCP server for tool discovery. The Agent may request access to a special tool discovery tool available via the Registry's MCP server. The tool discovery tool now has access to the Agent's scope (through the auth server including the scope in the response headers for the 200 OK) and applies the scopes while searching for potential tools that the Agent can have access to, thus it only lists the tools that the Agent has access to in its response via the tool discovery tool. Here is a example scenario, a general purpose AI assistant may be able to discover through the tool finder tool that there is a tool to get the current time at a given location but based on its access it may not have access to a tool to determine stock information and hence the Registry never list the stock information tool as an available tool to the Agent (if the Agent knows about this tool through some out of band mechanism and tries to invoke the tool it would get an access denied as explained in the previous steps).

The above implementation provides an OAuth compliant way to MCP security without the MCP servers being involved in enforcing this security greatly simplifying the MCP server implementation (as compared to every MCP server having to implement authentication and authorization).


## Amazon Cognito based reference implementation

This section discusses the reference implementation using Amazon Cognito as the IdP, supporting both Machine-to-Machine (M2M) and Session Cookie authentication methods.

### Key Components

#### 1. Auth Server (`auth_server/server.py`)
The enhanced auth server provides dual authentication support:
- **Primary Check**: Session cookie validation using `itsdangerous.URLSafeTimedSerializer`
- **Fallback**: JWT token validation with Cognito
- **Group Mapping**: Maps Cognito groups to MCP scopes
  - `mcp-admin` → Full unrestricted access
  - `mcp-user` → Restricted read access
  - `mcp-server-*` → Server-specific execute access

#### 2. CLI Authentication Tool (`auth_server/cli_auth.py`)
A standalone tool for user-based authentication:
- Implements OAuth 2.0 PKCE flow with Cognito hosted UI
- Opens browser for user authentication
- Runs local callback server on port 8080
- Creates session cookie compatible with registry format
- Saves to `~/.mcp/session_cookie` with secure permissions (0600)

#### 3. Enhanced Agent (`agents/agent_w_auth.py`)
The agent now supports both authentication methods:
- `--use-session-cookie` flag for session-based auth
- `--session-cookie-file` parameter (default: `~/.mcp/session_cookie`)
- Maintains full backward compatibility with M2M authentication
- Automatically includes appropriate headers based on auth method

### 1. Machine-to-Machine (M2M) Authentication

### 2. Session Cookie Authentication

Session cookie authentication enables agents to act on behalf of users, using their Cognito identity and group memberships for authorization.

#### Implementation Components

##### a. CLI Authentication Tool (`auth_server/cli_auth.py`)

The CLI tool handles the OAuth flow with Cognito and saves the session cookie locally:

```bash
# Run the CLI authentication tool
cd auth_server
python cli_auth.py

# This will:
# 1. Open your browser to Cognito hosted UI
# 2. After login, capture the authorization code
# 3. Exchange code for user information
# 4. Create and save session cookie to ~/.mcp/session_cookie
```

Required environment variables:
- `COGNITO_DOMAIN`: Your Cognito domain (e.g., 'mcp-gateway')
- `COGNITO_CLIENT_ID`: OAuth client ID configured for PKCE flow
- `SECRET_KEY`: Must match the registry's SECRET_KEY for cookie compatibility

##### b. Agent with Session Cookie Support

The enhanced agent (`agents/agent_w_auth.py`) now supports session cookie authentication:

```bash
# Use agent with session cookie
python agent_w_auth.py \
  --use-session-cookie \
  --message "What time is it in Tokyo?" \
  --mcp-registry-url http://localhost/mcpgw/sse
```

Key features:
- `--use-session-cookie`: Enable session cookie authentication mode
- `--session-cookie-file`: Cookie file path (default: `~/.mcp/session_cookie`)
- Automatically reads cookie and includes in request headers
- Falls back to M2M if session cookie flag not provided

##### c. Auth Server Enhancements

The auth server validates session cookies alongside JWT tokens:
- Checks for `mcp_gateway_session` cookie in request headers
- Validates cookie signature using `itsdangerous.URLSafeTimedSerializer`
- Maps Cognito groups to MCP scopes:
  - `mcp-admin` → unrestricted read/execute access
  - `mcp-user` → restricted read access
  - `mcp-server-{name}` → server-specific execute access
- Falls back to JWT validation if no valid cookie found

#### Advantages
1. Leverages existing Cognito user identities and groups
2. No need to manage separate M2M credentials for user-initiated actions
3. Maintains user context throughout the session
4. Compatible with existing web-based authentication flow
5. Auth server handles both authentication methods transparently

### 3. Machine-to-Machine Authentication

Cognito supports machine-to-machine authentication, enabling Agents to have their own identity separate from user identity.

#### Implementation Details:
- Reference: [AWS Blog on Machine-to-Machine Authentication](https://aws.amazon.com/blogs/mt/configuring-machine-to-machine-authentication-with-amazon-cognito-and-amazon-api-gateway-part-2/)
- Agents are treated as App Clients (Cognito terminology)
- MCP Server(s) function as resource servers

#### Authentication Flow:
1. Agent startup:
   - Configured with client ID, client secret, and a set of scopes
   - Requests scopes (e.g., MCP Registry with tool finder and basic MCP servers)
2. Cognito issues a JWT token
3. Agent includes the JWT token in MCP headers
4. Auth server on Nginx side:
   - Retrieves JWT token
   - Calls Cognito to validate token and get allowed scopes
   - Returns 200 or 403 based on:
     - URL (MCP server)
     - Payload (Tools)
     - Agent's allowed scopes

#### Advantages:
- Simpler implementation compared to user-based authentication
- Enables fine-grained control over Agent permissions
- Facilitates secure machine-to-machine communication within the MCP ecosystem

By implementing these enhancements, we can significantly improve the security, scalability, and flexibility of our MCP authentication and authorization system.