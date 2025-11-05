import { InvokeModelCommand } from "@aws-sdk/client-bedrock-runtime";
import { getBedrockClient } from "./bedrockClient.js";
import { getAnthropicClient } from "./anthropicClient.js";

export type ModelProvider = "bedrock" | "anthropic";

export interface MessageRequest {
  model: string;
  system: string;
  messages: any[];
  max_tokens: number;
  tools: any[];
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface MessageResponse {
  content: any[];
  stop_reason?: string;
  usage?: TokenUsage;
}

export async function sendMessage(
  provider: ModelProvider,
  request: MessageRequest
): Promise<MessageResponse> {
  if (provider === "bedrock") {
    return sendBedrockMessage(request);
  } else {
    return sendAnthropicMessage(request);
  }
}

async function sendBedrockMessage(request: MessageRequest): Promise<MessageResponse> {
  try {
    const client = getBedrockClient();

    // Prepare the request body for Bedrock
    const body = {
      anthropic_version: "bedrock-2023-05-31",
      max_tokens: request.max_tokens,
      system: request.system,
      messages: request.messages,
      tools: request.tools
    };

    const command = new InvokeModelCommand({
      modelId: request.model,
      contentType: "application/json",
      accept: "application/json",
      body: JSON.stringify(body)
    });

    const response = await client.send(command);
    const responseBody = JSON.parse(new TextDecoder().decode(response.body));

    // Extract token usage from Bedrock response
    const usage: TokenUsage | undefined = responseBody.usage ? {
      input_tokens: responseBody.usage.input_tokens || 0,
      output_tokens: responseBody.usage.output_tokens || 0,
      total_tokens: (responseBody.usage.input_tokens || 0) + (responseBody.usage.output_tokens || 0)
    } : undefined;

    return {
      content: responseBody.content || [],
      stop_reason: responseBody.stop_reason,
      usage
    };
  } catch (error: any) {
    // Provide helpful error messages for common Bedrock issues
    if (error.name === "AccessDeniedException") {
      throw new Error(
        "Amazon Bedrock access denied. Ensure your IAM user/role has 'bedrock:InvokeModel' permission and access to Claude models. " +
        "You may also need to enable model access in the Amazon Bedrock console."
      );
    } else if (error.name === "ResourceNotFoundException") {
      throw new Error(
        `Model '${request.model}' not found in your AWS region. Check that the model ID is correct and available in your region (${process.env.AWS_REGION || "us-east-1"}).`
      );
    } else if (error.name === "ValidationException") {
      throw new Error(
        "Invalid request to Amazon Bedrock. This might be due to an unsupported parameter or malformed request. " +
        "Error: " + error.message
      );
    }
    throw error;
  }
}

async function sendAnthropicMessage(request: MessageRequest): Promise<MessageResponse> {
  try {
    const client = getAnthropicClient();

    const response = await (client as any).beta.tools.messages.create({
      model: request.model,
      system: request.system,
      messages: request.messages,
      max_tokens: request.max_tokens,
      tools: request.tools
    });

    // Extract token usage from Anthropic API response
    const usage: TokenUsage | undefined = response.usage ? {
      input_tokens: response.usage.input_tokens || 0,
      output_tokens: response.usage.output_tokens || 0,
      total_tokens: (response.usage.input_tokens || 0) + (response.usage.output_tokens || 0)
    } : undefined;

    return {
      content: response.content || [],
      stop_reason: response.stop_reason,
      usage
    };
  } catch (error: any) {
    // Provide helpful error messages for Anthropic API issues
    if (error.status === 401) {
      throw new Error(
        "Anthropic API authentication failed. Check that your ANTHROPIC_API_KEY is valid."
      );
    } else if (error.status === 429) {
      throw new Error(
        "Anthropic API rate limit exceeded. Please wait a moment before trying again."
      );
    }
    throw error;
  }
}

export function getDefaultProvider(): ModelProvider {
  // Check if AWS credentials are configured
  const hasAwsCredentials = process.env.AWS_ACCESS_KEY_ID ||
                           process.env.AWS_SECRET_ACCESS_KEY ||
                           process.env.AWS_PROFILE;

  // Use Bedrock by default if AWS credentials are available
  if (hasAwsCredentials) {
    return "bedrock";
  }

  // Fall back to Anthropic if ANTHROPIC_API_KEY is set
  if (process.env.ANTHROPIC_API_KEY) {
    return "anthropic";
  }

  // Default to bedrock
  return "bedrock";
}

export function getDefaultModel(provider: ModelProvider): string {
  if (provider === "bedrock") {
    // Use environment variable or default to Claude Haiku 4.5 on Bedrock (fast and efficient)
    // Note: Claude 4+ models require inference profile IDs (us.anthropic.* or global.anthropic.*)
    // Claude 3.x models can use direct model IDs (anthropic.claude-*)
    return process.env.BEDROCK_MODEL_ID || "us.anthropic.claude-haiku-4-5-20251001-v1:0";
  } else {
    // Use environment variable or default to Haiku for Anthropic API
    return process.env.ANTHROPIC_MODEL || "claude-haiku-4-5-20251001";
  }
}
