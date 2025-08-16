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
graph TB
    %% Users and Agents at same level - stacked on top
    subgraph Clients["Client Layer"]
        direction TB
        User[User<br/>Human Administrator]
        CLIAuth[CLI Auth Tool]
        Agent[AI Agent]
        User --- CLIAuth
    end
    
    %% MCP Gateway & Registry Components (Separate)
    subgraph Infrastructure["MCP Gateway & Registry Infrastructure"]
        direction TB
        Nginx["Nginx<br/>Reverse Proxy"]
        AuthServer["Auth Server<br/>(Dual Auth)"]
        Registry["Registry<br/>Web UI"]
        RegistryMCP["Registry<br/>MCP Server"]
    end
    
    %% Identity Provider
    IdP[Identity Provider<br/>Amazon Cognito]
    
    %% MCP Server Farm
    subgraph MCPFarm["MCP Server Farm"]
        direction TB
        MCP1[MCP Server 1<br/>CurrentTime]
        MCP2[MCP Server 2<br/>FinInfo]
        MCP3[MCP Server 3<br/>Custom]
        MCPn[MCP Server n<br/>...]
    end
    
    %% All connections go through gateway/registry only
    User -->|1. Web UI access<br/>Server management| Nginx
    User -->|2. Registry access<br/>Tool discovery| Registry
    
    Agent -->|1. Discover tools<br/>with auth headers| Nginx
    Agent -->|2. MCP requests<br/>with auth headers| Nginx
    
    %% Internal routing
    Nginx -->|Route /mcpgw/*<br/>Auth validation| AuthServer
    Nginx -->|Route /mcpgw/*<br/>Tool discovery| RegistryMCP
    Nginx -->|Route /registry/*<br/>Web UI| Registry
    Nginx -->|Route /server1/*<br/>Proxy to MCP servers| MCP1
    Nginx -->|Route /server2/*<br/>Proxy to MCP servers| MCP2
    Nginx -->|Route /serverN/*<br/>Proxy to MCP servers| MCP3
    Nginx -->|Route /serverN/*<br/>Proxy to MCP servers| MCPn
    
    %% Auth flows
    IdP -.->|M2M: JWT tokens<br/>Client Credentials| Agent
    IdP -.->|User: OAuth PKCE flow<br/>Authorization Code| CLIAuth
    CLIAuth -.->|Session cookie<br/>Signed with SECRET_KEY| User
    AuthServer -.->|Validate JWT/cookies<br/>Get user groups/scopes| IdP
    
    %% Registry management (User-driven)
    Registry -->|Server registration<br/>Health monitoring| RegistryMCP
    RegistryMCP -->|Tool metadata<br/>Health checks| MCP1
    RegistryMCP -->|Tool metadata<br/>Health checks| MCP2
    RegistryMCP -->|Tool metadata<br/>Health checks| MCP3
    RegistryMCP -->|Tool metadata<br/>Health checks| MCPn
    
    %% Styling
    classDef userStyle fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    classDef agentStyle fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef clientStyle fill:#f5f5f5,stroke:#424242,stroke-width:2px
    classDef idpStyle fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef nginxStyle fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef authStyle fill:#ffebee,stroke:#c62828,stroke-width:2px
    classDef registryStyle fill:#fff8e1,stroke:#f57f17,stroke-width:2px
    classDef mcpStyle fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef cliStyle fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    
    class Clients clientStyle
    class User userStyle
    class Agent agentStyle
    class IdP idpStyle
    class Nginx nginxStyle
    class AuthServer authStyle
    class Registry,RegistryMCP registryStyle
    class MCP1,MCP2,MCP3,MCPn mcpStyle
    class CLIAuth cliStyle
```
### Architecture Components Explained

The updated architecture diagram above shows the clear separation of components that work together to provide secure, enterprise-ready MCP access:

#### Client Layer
- **User (Human Administrator)**: Manages the registry through the web UI, registers new MCP servers, and monitors system health
- **CLI Auth Tool**: Handles OAuth authentication flows for users, creating session cookies for web UI access
- **AI Agent**: Programmatic clients that discover and invoke MCP tools with proper authentication

#### MCP Gateway & Registry Infrastructure
- **Nginx Reverse Proxy**: Single entry point that routes all requests and handles SSL termination
- **Auth Server**: Validates JWT tokens and session cookies against Amazon Cognito, enforces fine-grained access control
- **Registry Web UI**: Administrative interface for managing MCP servers and viewing system status
- **Registry MCP Server**: Provides tool discovery capabilities to agents, returns filtered results based on permissions

#### External Components
- **Amazon Cognito**: Identity Provider (IdP) that handles user authentication and group management
- **MCP Server Farm**: Collection of individual MCP servers providing various tools and capabilities

> **For detailed setup instructions**, see the comprehensive guide in [`docs/cognito.md`](cognito.md) which covers both user identity and agent identity authentication modes.

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
        User->>CLIAuth: Run cli_user_auth.py
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

For comprehensive setup instructions and detailed configuration of Amazon Cognito as the Identity Provider, see the detailed documentation in [`docs/cognito.md`](cognito.md) which covers both user identity and agent identity authentication modes with step-by-step configuration guides.

For information about Fine-Grained Access Control (FGAC) including scope configuration, group mappings, and permission management, see [`docs/scopes.md`](scopes.md).

By implementing these enhancements, we can significantly improve the security, scalability, and flexibility of our MCP authentication and authorization system.