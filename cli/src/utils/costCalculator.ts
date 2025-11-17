import costData from './cost.json' with { type: 'json' };

interface ModelCost {
  input_cost_per_token?: number;
  output_cost_per_token?: number;
  cache_creation_input_token_cost?: number;
  cache_read_input_token_cost?: number;
}

/**
 * Calculate the total cost for a given model and token usage
 * @param modelId The model identifier (e.g., "us.anthropic.claude-haiku-4-5-20251001-v1:0")
 * @param inputTokens Number of input tokens used
 * @param outputTokens Number of output tokens used
 * @returns Total cost in dollars, or undefined if model cost data not found
 */
export function calculateCost(
  modelId: string,
  inputTokens: number,
  outputTokens: number
): number | undefined {
  const modelCostData = (costData as Record<string, ModelCost>)[modelId];

  if (!modelCostData) {
    return undefined;
  }

  const inputCostPerToken = modelCostData.input_cost_per_token ?? 0;
  const outputCostPerToken = modelCostData.output_cost_per_token ?? 0;

  const inputCost = inputTokens * inputCostPerToken;
  const outputCost = outputTokens * outputCostPerToken;
  const totalCost = inputCost + outputCost;

  return totalCost;
}

/**
 * Format cost as a readable string with appropriate precision
 * @param cost Cost in dollars
 * @returns Formatted string (e.g., "$0.0023" or "$0.00")
 */
export function formatCost(cost: number): string {
  if (cost >= 0.01) {
    return `$${cost.toFixed(2)}`;
  } else if (cost >= 0.001) {
    return `$${cost.toFixed(4)}`;
  } else if (cost > 0) {
    return `$${cost.toFixed(6)}`;
  } else {
    return "$0.00";
  }
}
