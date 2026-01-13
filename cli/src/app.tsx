import React, {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {Box, Text, useInput, Static} from "ink";
import TextInput from "ink-text-input";
import Spinner from "ink-spinner";
import {renderMarkdown, hasMarkdown, formatToolOutput} from "./utils/markdown.js";
import {Banner} from "./components/Banner.js";
import {CommandSuggestions} from "./components/CommandSuggestions.js";
import {TokenStatusFooter} from "./components/TokenStatusFooter.js";
import {getCommandSuggestions} from "./utils/commands.js";

import {resolveAuth} from "./auth.js";
import type {ParsedArgs} from "./parseArgs.js";
import {executeSlashCommand, overviewMessage} from "./commands/executor.js";
import {runAgentTurn} from "./agent/agentRunner.js";
import type {AgentMessage} from "./agent/agentRunner.js";
import type {CommandExecutionContext} from "./commands/executor.js";
import {getDefaultProvider, getDefaultModel} from "./agent/modelClient.js";
import {executeMcpCommand, formatMcpResult} from "./runtime/mcp.js";
import {refreshTokens, shouldRefreshToken} from "./utils/tokenRefresh.js";
import {calculateCost} from "./utils/costCalculator.js";

type ChatRole = "system" | "user" | "assistant" | "tool";

interface ChatMessage {
  id: number;
  role: ChatRole;
  text: string;
}

interface AuthReadyState {
  status: "ready";
  context: Awaited<ReturnType<typeof resolveAuth>>;
}

type AuthState = {status: "loading"} | AuthReadyState | {status: "error"; message: string};

interface AppProps {
  options: ParsedArgs;
}

export default function App({options}: AppProps) {
  const interactive = options.interactive !== false;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messageCounter = useRef(1);
  const [inputValue, setInputValue] = useState("");
  const [authState, setAuthState] = useState<AuthState>({status: "loading"});
  const [authAttempt, setAuthAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [initialised, setInitialised] = useState(false);
  const [hasShownWelcome, setHasShownWelcome] = useState(false);
  const [commandSuggestions, setCommandSuggestions] = useState<ReturnType<typeof getCommandSuggestions>>([]);
  const [selectedSuggestionIndex, setSelectedSuggestionIndex] = useState(0);

  // Token status state
  const [tokenSecondsRemaining, setTokenSecondsRemaining] = useState<number | undefined>();
  const [tokenExpired, setTokenExpired] = useState(false);
  const [isRefreshingToken, setIsRefreshingToken] = useState(false);
  const [lastTokenRefresh, setLastTokenRefresh] = useState<Date | undefined>();
  const [tokenSource, setTokenSource] = useState<string | undefined>();

  // Session token usage and cost tracking
  const [sessionInputTokens, setSessionInputTokens] = useState<number>(0);
  const [sessionOutputTokens, setSessionOutputTokens] = useState<number>(0);
  const [sessionTotalCost, setSessionTotalCost] = useState<number>(0);

  // Registry version
  const [registryVersion, setRegistryVersion] = useState<string | undefined>();

  const gatewayUrl = useMemo(() => options.url ?? "http://localhost/mcpgw/mcp", [options.url]);
  const gatewayBaseUrl = useMemo(() => deriveGatewayBase(gatewayUrl), [gatewayUrl]);
  const agentAvailable = useMemo(() => {
    // Check credentials: AWS Profile, Anthropic API key, or default to true
    // (let AWS SDK discover execution role credentials at runtime)
    const hasAwsProfile = Boolean(process.env.AWS_PROFILE);
    const hasAnthropicKey = Boolean(process.env.ANTHROPIC_API_KEY);

    // If no explicit credentials, assume execution role is available
    // AWS SDK will attempt to get credentials from EC2 instance metadata
    return hasAwsProfile || hasAnthropicKey || true;
  }, []);

  const addMessage = useCallback((role: ChatRole, text: string) => {
    const id = messageCounter.current++;
    setMessages((prev) => [...prev, {id, role, text}]);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setAuthState({status: "loading"});

    // Try to resolve auth, and if it fails due to missing/invalid tokens, automatically refresh
    resolveAuth({
      tokenFile: options.tokenFile,
      explicitToken: options.token,
      cwd: process.cwd()
    })
      .then(async (context) => {
        if (cancelled) return;

        // Check if we have a gateway token - if not, try to generate one
        if (!context.gatewayToken || context.gatewaySource === "none") {
          addMessage("assistant", "No gateway token found. Attempting automatic generation...");

          try {
            const result = await refreshTokens();
            if (result.success) {
              addMessage("assistant", "✅ OAuth tokens generated successfully. Authenticating...");
              // Trigger auth reload
              setAuthAttempt((attempt) => attempt + 1);
            } else {
              setAuthState({status: "error", message: `Token generation failed: ${result.message}`});
            }
          } catch (refreshError) {
            setAuthState({status: "error", message: `Token generation failed: ${(refreshError as Error).message}`});
          }
          return;
        }

        setAuthState({status: "ready", context});
      })
      .catch(async (error: unknown) => {
        if (cancelled) return;

        const errorMessage = (error as Error).message;

        // If auth failed due to missing or invalid tokens, try to refresh automatically
        if (errorMessage.includes("token") || errorMessage.includes("ENOENT") || errorMessage.includes("Failed to load")) {
          addMessage("assistant", "OAuth tokens missing or invalid. Attempting automatic generation...");

          try {
            const result = await refreshTokens();
            if (result.success) {
              addMessage("assistant", "✅ OAuth tokens generated successfully. Authenticating...");
              // Trigger auth reload
              setAuthAttempt((attempt) => attempt + 1);
            } else {
              setAuthState({status: "error", message: `Token generation failed: ${result.message}`});
            }
          } catch (refreshError) {
            setAuthState({status: "error", message: `Token generation failed: ${(refreshError as Error).message}`});
          }
        } else {
          setAuthState({status: "error", message: errorMessage});
        }
      });
    return () => {
      cancelled = true;
    };
  }, [options.token, options.tokenFile, authAttempt, addMessage]);

  useEffect(() => {
    if (authState.status === "ready" && !initialised) {
      // Only show welcome messages the first time
      if (!hasShownWelcome) {
        const infoLines = summariseAuth(authState, gatewayUrl);
        infoLines.forEach((line) => addMessage("assistant", line));
        setHasShownWelcome(true);
      }
      setInitialised(true);

      // Initialize token status
      const gatewayInspection = authState.context.inspections.find(i => i.label.includes("Gateway"));
      if (gatewayInspection && shouldRefreshToken(gatewayInspection.secondsRemaining)) {
        refreshTokens()
          .then((result) => {
            if (result.success) {
              // Silently refresh tokens without showing messages
              // Trigger auth reload
              setAuthAttempt((attempt) => attempt + 1);
            } else {
              addMessage("assistant", `❌ ${result.message}. Please run: ./credentials-provider/generate_creds.sh --ingress-only`);
            }
          })
          .catch((error) => {
            addMessage("assistant", `❌ Token refresh failed: ${error.message}. Please run: ./credentials-provider/generate_creds.sh --ingress-only`);
          });
      }

      // Fetch registry version
      fetch(`${gatewayBaseUrl}/api/version`)
        .then(res => res.json())
        .then(data => setRegistryVersion(data.version))
        .catch(() => {
          // Silently fail if version fetch fails
        });
    }
  }, [authState, addMessage, initialised, gatewayUrl, gatewayBaseUrl, setAuthAttempt, hasShownWelcome]);

  useEffect(() => {
    if (!interactive && authState.status === "ready" && options.command) {
      const command = options.command;
      (async () => {
        try {
          const extras = options.tool
            ? {
                tool: options.tool,
                args: options.args ? JSON.parse(options.args) : {}
              }
            : undefined;
          const result = await executeMcpCommand(
            command,
            gatewayUrl,
            authState.context.gatewayToken,
            authState.context.backendToken,
            extras
          );
          const lines = formatMcpResult(command, result.handshake, result.response, options.tool);
          // eslint-disable-next-line no-console
          console.log(options.json ? JSON.stringify({lines}) : lines.join("\n"));
          process.exit(0);
        } catch (error) {
          // eslint-disable-next-line no-console
          console.error((error as Error).message);
          process.exit(1);
        }
      })();
    }
  }, [authState, gatewayUrl, interactive, options]);

  // Update command suggestions when input changes
  useEffect(() => {
    if (inputValue.startsWith("/")) {
      const suggestions = getCommandSuggestions(inputValue);
      setCommandSuggestions(suggestions);
      setSelectedSuggestionIndex(0);
    } else {
      setCommandSuggestions([]);
      setSelectedSuggestionIndex(0);
    }
  }, [inputValue]);

  // Timer effect to update token status every second
  useEffect(() => {
    if (authState.status !== "ready") return;

    const gatewayInspection = authState.context.inspections.find(i => i.label.includes("Gateway"));
    if (gatewayInspection) {
      // Initialize token status on mount
      const now = Date.now() / 1000;
      const expiresAt = gatewayInspection.expiresAt ? gatewayInspection.expiresAt.getTime() / 1000 : 0;
      const remaining = Math.floor(expiresAt - now);
      setTokenSecondsRemaining(remaining);
      setTokenExpired(remaining <= 0);
      setTokenSource(authState.context.gatewaySource);
    }

    const interval = setInterval(() => {
      if (authState.status !== "ready") return;

      const gatewayInspection = authState.context.inspections.find(i => i.label.includes("Gateway"));
      if (gatewayInspection) {
        const now = Date.now() / 1000;
        const expiresAt = gatewayInspection.expiresAt ? gatewayInspection.expiresAt.getTime() / 1000 : 0;
        const remaining = Math.floor(expiresAt - now);
        setTokenSecondsRemaining(remaining);
        setTokenExpired(remaining <= 0);

        // Auto-refresh when <= 10 seconds remaining
        if (shouldRefreshToken(remaining) && !isRefreshingToken) {
          setIsRefreshingToken(true);
          refreshTokens()
            .then((result) => {
              if (result.success) {
                setLastTokenRefresh(new Date());
                // Trigger auth reload
                setAuthAttempt((attempt) => attempt + 1);
                setInitialised(false);
              }
              setIsRefreshingToken(false);
            })
            .catch(() => {
              setIsRefreshingToken(false);
            });
        }
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [authState, isRefreshingToken, setAuthAttempt]);

  useInput(
    (input, key) => {
      if (key.ctrl && input === "c") {
        process.exit();
      }

      // Handle arrow keys for command suggestions
      if (commandSuggestions.length > 0) {
        if (key.upArrow) {
          setSelectedSuggestionIndex((prev) =>
            prev > 0 ? prev - 1 : commandSuggestions.length - 1
          );
        } else if (key.downArrow) {
          setSelectedSuggestionIndex((prev) =>
            prev < commandSuggestions.length - 1 ? prev + 1 : 0
          );
        } else if (key.tab || key.return) {
          // Tab or Enter to autocomplete
          const selected = commandSuggestions[selectedSuggestionIndex];
          if (selected) {
            setInputValue(selected.command + " ");
          }
          // Prevent Enter from submitting when autocompleting
          if (key.return) {
            return;
          }
        }
      }
    },
    {isActive: interactive}
  );

  const handleSubmit = useCallback(
    async (value: string) => {
      // If suggestions are visible, don't submit - let Enter autocomplete instead
      if (commandSuggestions.length > 0) {
        return;
      }

      const trimmed = value.trim();
      if (!trimmed) {
        return;
      }

      setInputValue("");

      const userMessage: ChatMessage = {id: messageCounter.current++, role: "user", text: trimmed};
      setMessages((prev) => [...prev, userMessage]);

      if (trimmed === "/retry") {
        setAuthAttempt((attempt) => attempt + 1);
        setInitialised(false);
        addMessage("assistant", "Retrying authentication...");
        return;
      }

      if (trimmed === "/refresh-tokens" || trimmed === "/refresh") {
        setBusy(true);
        refreshTokens()
          .then((result) => {
            if (result.success) {
              addMessage("assistant", "✅ OAuth tokens refreshed successfully. Reloading authentication...");
              setAuthAttempt((attempt) => attempt + 1);
              setInitialised(false);
            } else {
              addMessage("assistant", `❌ ${result.message}. Try running: ./credentials-provider/generate_creds.sh --ingress-only`);
            }
          })
          .catch((error) => {
            addMessage("assistant", `❌ Token refresh failed: ${error.message}`);
          })
          .finally(() => {
            setBusy(false);
          });
        return;
      }

      if (authState.status !== "ready") {
        addMessage("assistant", "Authentication is not ready yet. Try /retry or wait a moment.");
        return;
      }

      // Token refresh is now handled automatically by the timer effect in the footer

      const commandContext: CommandExecutionContext = {
        gatewayUrl,
        gatewayBaseUrl,
        gatewayToken: authState.context.gatewayToken,
        backendToken: authState.context.backendToken
      };

      const history: AgentMessage[] = buildAgentHistory([...messages, userMessage]);

      if (trimmed.startsWith("/")) {
        setBusy(true);
        try {
          const result = await executeSlashCommand(trimmed, commandContext);
          addMessage(result.isError ? "assistant" : "tool", result.lines.join("\n"));

          // Handle exit command
          if (result.shouldExit) {
            setTimeout(() => process.exit(0), 500);
          }
        } catch (error) {
          addMessage("assistant", `Command failed: ${(error as Error).message}`);
        } finally {
          setBusy(false);
        }
        return;
      }

      if (!agentAvailable) {
        addMessage(
          "assistant",
          "Agent mode is disabled. Configure AWS_PROFILE, ensure execution role is available, or set ANTHROPIC_API_KEY. Alternatively, use slash commands like /ping."
        );
        return;
      }

      setBusy(true);
      try {
        const result = await runAgentTurn(history, {
          gatewayUrl,
          gatewayBaseUrl,
          gatewayToken: authState.context.gatewayToken,
          backendToken: authState.context.backendToken,
          model: process.env.ANTHROPIC_MODEL
        });

        // Only show tool outputs if there's an error (for debugging)
        result.toolOutputs.forEach((tool) => {
          if (tool.isError) {
            const formatted = formatToolOutput(tool.name, tool.output, tool.isError);
            addMessage("tool", formatted);
          }
        });

        if (result.messages.length === 0) {
          addMessage("assistant", "No response from the agent. Try a different prompt or use /help.");
        } else {
          result.messages.forEach((msg) => addMessage(msg.role, msg.content));

          // Track token usage and cost
          if (result.tokenUsage) {
            const {input_tokens, output_tokens, total_tokens} = result.tokenUsage;

            // Get the current model being used
            const currentModel = process.env.ANTHROPIC_MODEL || getDefaultModel(getDefaultProvider());

            // Calculate cost for this turn
            const turnCost = calculateCost(currentModel, input_tokens, output_tokens);

            // Update session totals
            setSessionInputTokens((prev) => prev + input_tokens);
            setSessionOutputTokens((prev) => prev + output_tokens);
            if (turnCost !== undefined) {
              setSessionTotalCost((prev) => prev + turnCost);
            }
          }
        }
      } catch (error) {
        addMessage("assistant", `Agent error: ${(error as Error).message}`);
      } finally {
        setBusy(false);
      }
    },
    [messages, authState, gatewayUrl, gatewayBaseUrl, agentAvailable, addMessage, commandSuggestions]
  );

  const renderMessages = () => {
    const items = [{id: 0, type: 'banner' as const}, ...messages.map(m => ({...m, type: 'message' as const}))];
    return (
      <Static items={items}>
        {(item) => {
          if (item.type === 'banner') {
            return <Banner key="banner" />;
          }
          return (
            <Box key={item.id} flexDirection="column" marginBottom={1}>
              <MessageBubble role={item.role} text={item.text} />
            </Box>
          );
        }}
      </Static>
    );
  };

  const inputPrompt = useMemo(() => {
    if (busy) {
      return (
        <Text color="yellow">
          <Spinner type="dots" /> Working...
        </Text>
      );
    }
    if (authState.status === "loading") {
      return (
        <Text color="cyan">
          <Spinner type="dots" /> Authenticating...
        </Text>
      );
    }
    if (authState.status === "error") {
      return <Text color="red">Auth error. Type /retry once credentials are fixed.</Text>;
    }
    return <Text color="cyan">›</Text>;
  }, [authState, busy]);

  if (!interactive) {
    if (authState.status === "loading") {
      return (
        <Box>
          <Text>Authenticating...</Text>
        </Box>
      );
    }
    if (authState.status === "error") {
      return (
        <Box>
          <Text color="red">Authentication failed: {authState.message}</Text>
        </Box>
      );
    }
    return (
      <Box>
        <Text>Processing non-interactive command...</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" gap={1}>
      {renderMessages()}
      {commandSuggestions.length > 0 && (
        <CommandSuggestions
          suggestions={commandSuggestions}
          selectedIndex={selectedSuggestionIndex}
        />
      )}
      <Box flexDirection="column" marginTop={1}>
        <Box>
          <Text color="gray">{"═".repeat(Math.min(process.stdout.columns || 80, 80))}</Text>
        </Box>
        <Box>
          {inputPrompt}
          <Box marginLeft={1} flexGrow={1}>
            <Box>
              <TextInput
                value={inputValue}
                onChange={setInputValue}
                onSubmit={handleSubmit}
                placeholder="Type a message or use /commands"
              />
              {commandSuggestions.length > 0 && commandSuggestions[selectedSuggestionIndex] && (
                <Text color="gray" dimColor>
                  {commandSuggestions[selectedSuggestionIndex].command.substring(inputValue.length)}
                </Text>
              )}
            </Box>
          </Box>
        </Box>
        <Box>
          <Text color="gray">{"═".repeat(Math.min(process.stdout.columns || 80, 80))}</Text>
        </Box>
        {commandSuggestions.length > 0 && commandSuggestions[selectedSuggestionIndex] && (
          <Box marginTop={1}>
            <Text color="cyan" dimColor>
              {commandSuggestions[selectedSuggestionIndex].command}
            </Text>
            <Text color="gray" dimColor>
              {" — "}
              {commandSuggestions[selectedSuggestionIndex].description}
            </Text>
          </Box>
        )}
        {authState.status === "ready" && (
          <Box marginTop={1}>
            <TokenStatusFooter
              secondsRemaining={tokenSecondsRemaining}
              expired={tokenExpired}
              isRefreshing={isRefreshingToken}
              lastRefresh={lastTokenRefresh}
              source={tokenSource}
              model={getDefaultModel(getDefaultProvider())}
              inputTokens={sessionInputTokens}
              outputTokens={sessionOutputTokens}
              cost={sessionTotalCost}
              registryVersion={registryVersion}
            />
          </Box>
        )}
      </Box>
    </Box>
  );
}

function buildAgentHistory(messages: ChatMessage[]): AgentMessage[] {
  return messages
    .filter((message) => message.role !== "tool")
    .map((message) => ({
      role:
        message.role === "system"
          ? "system"
          : message.role === "assistant"
            ? "assistant"
            : "user",
      content: message.text
    }));
}

function summariseAuth(_authState: AuthReadyState, gatewayUrl: string): string[] {
  // Simplified - only show gateway URL and help. Token/model info shown in footer
  const lines = [`Authenticated against ${gatewayUrl}`];
  lines.push("");
  lines.push(overviewMessage());
  return lines;
}

interface MessageBubbleProps {
  role: ChatRole;
  text: string;
}

function MessageBubble({role, text}: MessageBubbleProps) {
  const color = roleColor(role);
  const label = roleLabel(role);

  // Render markdown for assistant and tool messages
  const shouldRenderMarkdown = (role === "assistant" || role === "tool") && hasMarkdown(text);
  const displayText = shouldRenderMarkdown ? renderMarkdown(text) : text;

  // Helper to render text with inline code highlighting
  const renderTextWithHighlights = (content: string) => {
    const parts = content.split(/(`[^`]+`)/g);
    return parts.map((part, i) => {
      if (part.startsWith('`') && part.endsWith('`')) {
        // Remove backticks and render in cyan
        return (
          <Text key={i} color="cyan" bold>
            {part.slice(1, -1)}
          </Text>
        );
      }
      return <Text key={i}>{part}</Text>;
    });
  };

  return (
    <Box flexDirection="column">
      <Box marginBottom={0}>
        <Text bold color={color}>
          {label}
        </Text>
      </Box>
      <Box paddingLeft={2}>
        <Text color={color === "magenta" ? "gray" : undefined}>
          {renderTextWithHighlights(displayText)}
        </Text>
      </Box>
    </Box>
  );
}

function roleLabel(role: ChatRole): string {
  switch (role) {
    case "user":
      return "You";
    case "assistant":
      return "Assistant";
    case "tool":
      return "Tool";
    case "system":
    default:
      return "System";
  }
}

function roleColor(role: ChatRole): string | undefined {
  switch (role) {
    case "user":
      return "green";
    case "assistant":
      return "cyan";
    case "tool":
      return "yellow";
    case "system":
    default:
      return "magenta";
  }
}

function deriveGatewayBase(url: string): string {
  if (!url) {
    return "";
  }
  try {
    const parsed = new URL(url);
    const pathname = parsed.pathname.replace(/\/mcpgw\/mcp(?:\/.*)?$/, "");
    return `${parsed.origin}${pathname.endsWith("/") || pathname.length === 0 ? pathname : `${pathname}/`}`;
  } catch {
    return url.replace(/\/mcpgw\/mcp(?:\/.*)?$/, "");
  }
}
