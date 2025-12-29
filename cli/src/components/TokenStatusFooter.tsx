import {Box, Text} from "ink";

interface TokenStatusFooterProps {
  secondsRemaining?: number;
  expired: boolean;
  isRefreshing: boolean;
  lastRefresh?: Date;
  source?: string;
  model?: string;
  inputTokens?: number;
  outputTokens?: number;
  cost?: number;
  registryVersion?: string;
}

export function TokenStatusFooter({
  secondsRemaining,
  expired,
  isRefreshing,
  lastRefresh,
  source,
  model,
  inputTokens,
  outputTokens,
  cost,
  registryVersion
}: TokenStatusFooterProps) {
  const formatTime = (seconds: number): string => {
    if (seconds < 0) return "expired";
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  const getStatusText = (): string => {
    if (isRefreshing) return "Refreshing...";
    if (expired || (secondsRemaining !== undefined && secondsRemaining <= 0)) return "Expired";
    if (secondsRemaining !== undefined) return `Valid for ${formatTime(secondsRemaining)}`;
    return "Unknown";
  };

  const getStatusColor = (): string => {
    if (isRefreshing) return "cyan";
    if (expired || (secondsRemaining !== undefined && secondsRemaining <= 0)) return "red";
    if (secondsRemaining !== undefined && secondsRemaining < 60) return "yellow";
    return "green";
  };

  const lastRefreshText = lastRefresh
    ? lastRefresh.toLocaleTimeString("en-US", {hour12: false})
    : "N/A";

  const formatCost = (costValue: number): string => {
    if (costValue >= 0.01) {
      return `$${costValue.toFixed(2)}`;
    } else if (costValue >= 0.001) {
      return `$${costValue.toFixed(4)}`;
    } else if (costValue > 0) {
      return `$${costValue.toFixed(6)}`;
    } else {
      return "$0.00";
    }
  };

  return (
    <Box flexDirection="row" gap={1}>
      <Text color={getStatusColor()}>
        Token: {getStatusText()}
      </Text>
      {source && (
        <Text>
          <Text color="gray"> | Source: </Text>
          <Text color="cyan">{source}</Text>
        </Text>
      )}
      <Text>
        <Text color="gray"> | Last refresh: </Text>
        <Text color="cyan">{lastRefreshText}</Text>
      </Text>
      {model && (
        <Text>
          <Text color="gray"> | Model: </Text>
          <Text color="cyan">{model}</Text>
        </Text>
      )}
      {(inputTokens !== undefined || outputTokens !== undefined) && (inputTokens! > 0 || outputTokens! > 0) && (
        <Text>
          <Text color="gray"> | Tokens: </Text>
          <Text color="cyan">In: {(inputTokens || 0).toLocaleString()}</Text>
          <Text color="gray"> | </Text>
          <Text color="cyan">Out: {(outputTokens || 0).toLocaleString()}</Text>
        </Text>
      )}
      {cost !== undefined && cost > 0 && (
        <Text>
          <Text color="gray"> | Cost: </Text>
          <Text color="cyan">{formatCost(cost)}</Text>
        </Text>
      )}
      {registryVersion && (
        <Text>
          <Text color="gray"> | Registry: </Text>
          <Text color="magenta">{registryVersion}</Text>
        </Text>
      )}
    </Box>
  );
}
