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
    
    %% Identity Provider
    IdP[Identity Provider]
    
    %% Gateway and Registry Block
    subgraph GwReg["Gateway & Registry"]
        Gateway["Gateway<br/>(Reverse Proxy)"]
        Registry[Registry]
        AuthServer["Auth Server"]
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
    IdP -.->|Identity/tokens| Agent
    AuthServer -.->|Validate tokens| IdP
    
    %% Styling
    classDef agentStyle fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef idpStyle fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef gwregStyle fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef mcpStyle fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    
    class Agent agentStyle
    class IdP idpStyle
    class Gateway,Registry,AuthServer gwregStyle
    class MCP1,MCP2,MCP3,MCPn mcpStyle
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
    alt Agent Identity
        Agent->>IdP: Request auth credentials
        IdP->>Agent: Return credentials + metadata
    else On-behalf of User
        User->>IdP: Sign-in (web/CLI)
        IdP->>User: Return credentials + metadata
        User->>Agent: Provide credentials
    end

    %% Step 2: Embed credentials in headers
    Note over Agent: Step 2: Embed credentials + IdP metadata

    %% Step 3: Tool Discovery with scoped access
    Note over Agent,Registry: Step 3: Scoped Tool Discovery
    Agent->>Gateway: Tool discovery request with auth headers
    Gateway->>AuthServer: Validate credentials
    AuthServer->>IdP: Verify credentials
    IdP->>AuthServer: Auth response + scope
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


## Amazon Cognito based reference implementation (_work in progress_)

This section discusses a reference implementation using Amazon Cognito as the IdP.

### Agent uses on-behalf of identity

### 1. Session Cookie Implementation

The proposed session cookie approach, which encodes user metadata from Cognito, is a valuable addition to our system. However, there are two crucial considerations:

#### a. Out-of-Band Cookie Retrieval

- A separate CLI tool will be required to run before the agent execution.
- Process:
  1. CLI opens the browser
  2. User authenticates
  3. Cookie is retrieved and stored in a local file
  4. Agent reads the cookie from the local file
  5. Agent uses the cookie in the MCP client

#### b. Validation Server Implementation

- A dedicated Validation Server (Auth Server) will handle cookie validation instead of the Registry.
- Key points:
  - Runs in a container, accessible at port 8888
  - Performs the same functionality as current `main.py`, `auth`, and related modules
  - Triggered by an auth command in the Nginx location section for each server
  - Creates a pipeline:
    1. Request goes to the Validation Server first
    2. If Validation Server returns 200 OK, request proceeds to the MCP server
  - MCP server remains unburdened by authentication tasks

#### Advantages:
1. Eliminates need for MCP client in Registry for every client-server communication
2. Maintains Registry as a control plane application
3. Improves scalability
4. Auth server can scale independently in the future
5. Simplifies MCP servers by removing authentication responsibilities

### 2. Machine-to-Machine Authentication

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